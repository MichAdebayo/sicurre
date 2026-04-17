"""Run the database-historical cron feed.

This scheduler intentionally stops at raw ingestion:

1. append a cron-sized synthetic batch into the external feeder DB
2. ingest only the new feeder rows into the receiving Sicurre DB

It does not normalize, annotate, or rebuild datasets.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)  # noqa: E402

from core.config import get_settings  # noqa: E402
from core.database import Base  # noqa: E402
from data_platform.extractors.legacy_db import (
    LegacyDbConnector,
    LegacyDbIngestionService,
)  # noqa: E402
from data_platform.services.external_db_cron_feed import (  # noqa: E402
    DEFAULT_CLASS_COUNTS,
    DEFAULT_CRON_FEED_DB_URL,
    append_cron_generation_batch,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

_CRON_CLASS_ORDER: tuple[str, ...] = ("phishing", "spam", "legitimate")


def _to_async_sqlite_url(db_url: str) -> str:
    if db_url.startswith("sqlite+aiosqlite://"):
        return db_url
    if db_url.startswith("sqlite://"):
        return db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return db_url


def _resolve_class_counts(
    *,
    total_count: int | None,
    phishing_count: int | None,
    spam_count: int | None,
    legitimate_count: int | None,
    default_total_count: int,
    max_total_count: int,
) -> dict[str, int]:
    explicit_counts = {
        "phishing": phishing_count,
        "spam": spam_count,
        "legitimate": legitimate_count,
    }
    explicit_values = [count for count in explicit_counts.values() if count is not None]

    if max_total_count <= 0:
        raise ValueError(f"max_total_count must be positive, got {max_total_count}")

    if total_count is not None and explicit_values:
        raise ValueError(
            "Use either --total-count or explicit per-class counts, not both."
        )

    if total_count is None and not explicit_values:
        if default_total_count <= 0:
            raise ValueError(
                f"default_total_count must be positive, got {default_total_count}"
            )
        total_count = default_total_count

    if total_count is not None:
        if total_count <= 0:
            raise ValueError(f"total_count must be positive, got {total_count}")
        base, remainder = divmod(total_count, len(_CRON_CLASS_ORDER))
        resolved = {label: base for label in _CRON_CLASS_ORDER}
        for index in range(remainder):
            resolved[_CRON_CLASS_ORDER[index]] += 1
    elif explicit_values:
        resolved = {
            label: int(explicit_counts[label] or 0) for label in _CRON_CLASS_ORDER
        }
        if any(count < 0 for count in resolved.values()):
            raise ValueError(f"class counts must be >= 0, got {resolved}")
        if sum(resolved.values()) <= 0:
            raise ValueError("at least one class count must be positive")
    else:
        resolved = dict(DEFAULT_CLASS_COUNTS)

    resolved_total = sum(resolved.values())
    if resolved_total > max_total_count:
        raise ValueError(
            f"requested total {resolved_total} exceeds max_total_count {max_total_count}"
        )

    return resolved


async def main(
    *,
    trigger_mode: str,
    external_db_url: str,
    class_counts: dict[str, int],
    seed: int | None,
) -> None:
    settings = get_settings()
    logger.info("Using receiving Sicurre DB: %s", settings.database_url)
    logger.info("Using external feeder DB: %s", external_db_url)

    feed_result = append_cron_generation_batch(
        db_url=external_db_url,
        class_counts=class_counts,
        seed=seed,
    )

    engine = create_async_engine(settings.database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    service = LegacyDbIngestionService(
        connector=LegacyDbConnector(db_url=_to_async_sqlite_url(external_db_url))
    )
    async with session_factory() as session:
        ingest_result = await service.run(session, trigger_mode=trigger_mode)

    print(
        "database-historical cron feed completed",
        f"seed={feed_result.seed}",
        f"inserted_total={feed_result.inserted_total}",
        f"inserted_by_class={feed_result.inserted_by_class}",
        f"used_scenarios={feed_result.used_scenario_count}/{feed_result.scenario_catalog_size}",
        f"external_db={external_db_url}",
    )
    print(ingest_result.log_message or "DB ingestion completed")
    print(
        f"  new={ingest_result.raw_record_count}"
        f"  skipped={ingest_result.skipped_count}"
        f"  extracted={ingest_result.total_extracted_count}"
        f"  objects={ingest_result.raw_object_count}"
    )
    if ingest_result.snapshot_storage_uri:
        print(f"  snapshot={ingest_result.snapshot_storage_uri}")

    await engine.dispose()


if __name__ == "__main__":
    settings = get_settings()
    parser = argparse.ArgumentParser(description="database-historical cron feed")
    parser.add_argument(
        "--trigger",
        default="scheduled",
        choices=["manual", "scheduled"],
        help="Trigger mode written to the receiving ingestion run",
    )
    parser.add_argument(
        "--external-db-url",
        default=DEFAULT_CRON_FEED_DB_URL,
        help=(
            "Sync SQLAlchemy URL for the cron feeder DB. "
            f"Defaults to {DEFAULT_CRON_FEED_DB_URL}."
        ),
    )
    parser.add_argument(
        "--total-count",
        type=int,
        default=None,
        help=(
            "Total number of rows to append before ingestion. "
            "Distributed as evenly as possible across phishing, spam, and legitimate. "
            "If omitted, the scheduler uses SICURRE_DATABASE_HISTORICAL_CRON_TOTAL_COUNT."
        ),
    )
    parser.add_argument(
        "--phishing-count",
        type=int,
        default=None,
        help="Number of phishing rows to append before ingestion. Overrides --total-count and env default.",
    )
    parser.add_argument(
        "--spam-count",
        type=int,
        default=None,
        help="Number of spam rows to append before ingestion. Overrides --total-count and env default.",
    )
    parser.add_argument(
        "--legitimate-count",
        type=int,
        default=None,
        help="Number of legitimate rows to append before ingestion. Overrides --total-count and env default.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional deterministic seed for the synthetic feeder batch.",
    )
    args = parser.parse_args()
    class_counts = _resolve_class_counts(
        total_count=args.total_count,
        phishing_count=args.phishing_count,
        spam_count=args.spam_count,
        legitimate_count=args.legitimate_count,
        default_total_count=settings.database_historical_cron_total_count,
        max_total_count=settings.database_historical_cron_max_total_count,
    )

    asyncio.run(
        main(
            trigger_mode=args.trigger,
            external_db_url=args.external_db_url,
            class_counts=class_counts,
            seed=args.seed,
        )
    )
