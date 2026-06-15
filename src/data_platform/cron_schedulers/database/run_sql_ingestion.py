"""Run the incremental SQL cron ingestion from the external threat database.

This orchestrator:
1. Forces snapshot storage to R2 under cron/db/external_threats (or reserved/).
2. Retrieves the maximum created_at (watermark) currently in the DB.
3. Fetches new records from external_threats.db using the watermark.
4. Saves a JSON snapshot to R2 and writes raw records to the platform.

Pass --reserved to write under cron/reserved/db/external_threats/ instead.
"""

from __future__ import annotations

import argparse as _argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Reserved-slot routing (must happen before settings are loaded) ─────────────
_parser = _argparse.ArgumentParser(add_help=False)
_parser.add_argument("--reserved", action="store_true", default=False)
_reserved_args, _ = _parser.parse_known_args()

# Force snapshot storage to R2 under the appropriate cron prefix
os.environ["SICURRE_DATABASE_HISTORICAL_SNAPSHOT_STORAGE_BACKEND"] = "prod"
os.environ["SICURRE_DATABASE_HISTORICAL_SNAPSHOT_PREFIX"] = (
    "cron/reserved/db/external_threats"
    if _reserved_args.reserved
    else "cron/db/external_threats"
)
# ──────────────────────────────────────────────────────────────────────────────

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import get_settings
from core.database import Base
from data_platform.extractors.legacy_db import LegacyDbIngestionService
from data_platform.services.database.cron_feed import append_cron_generation_batch
from db.models import PipelineState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

_CRON_GENERATION_LABELS: tuple[str, ...] = ("phishing", "spam", "legitimate")


def _build_generation_counts(total_count: int) -> dict[str, int]:
    base_count, remainder = divmod(total_count, len(_CRON_GENERATION_LABELS))
    counts = {label: base_count for label in _CRON_GENERATION_LABELS}
    for index in range(remainder):
        counts[_CRON_GENERATION_LABELS[index]] += 1
    return counts


def _resolve_class_counts(
    total_count: int | None,
    phishing_count: int | None,
    spam_count: int | None,
    legitimate_count: int | None,
    default_total_count: int,
    max_total_count: int,
) -> dict[str, int]:
    if total_count is not None and (
        phishing_count is not None
        or spam_count is not None
        or legitimate_count is not None
    ):
        raise ValueError("Specify either --total-count or explicit class counts, not both")

    if (
        phishing_count is not None
        or spam_count is not None
        or legitimate_count is not None
    ):
        phishing = phishing_count or 0
        spam = spam_count or 0
        legitimate = legitimate_count or 0
        resolved_total = phishing + spam + legitimate
    else:
        resolved_total = total_count if total_count is not None else default_total_count

    if resolved_total > max_total_count:
        raise ValueError(
            f"Requested count {resolved_total} exceeds max_total_count {max_total_count}"
        )

    # Distribute the total balanced across classes
    base_count, remainder = divmod(resolved_total, 3)
    counts = {
        "phishing": base_count,
        "spam": base_count,
        "legitimate": base_count,
    }
    # distribute remainder to phishing then spam
    if remainder > 0:
        counts["phishing"] += 1
    if remainder > 1:
        counts["spam"] += 1

    return counts


async def run_incremental_sql_cron() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.data_platform_database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    pipeline_name = "sql_cron"

    async with session_factory() as session:
        stmt = select(PipelineState).where(PipelineState.pipeline_name == pipeline_name)
        row = await session.scalar(stmt)
        if row is None:
            last_known_date = "1970-01-01 00:00:00"
        else:
            last_known_date = row.state_data.get(
                "last_created_at", "1970-01-01 00:00:00"
            )

    logger.info("SQL Cron last known created_at: %s", last_known_date)

    requested_total_count = settings.database_historical_cron_total_count
    max_total_count = settings.database_historical_cron_max_total_count
    if requested_total_count < 0:
        raise ValueError("SICURRE_DATABASE_HISTORICAL_CRON_TOTAL_COUNT must be >= 0")

    generated_total_count = 0
    if requested_total_count > 0:
        effective_total_count = min(requested_total_count, max_total_count)
        if effective_total_count != requested_total_count:
            logger.warning(
                "Clamping requested SQL cron generation batch from %d to %d",
                requested_total_count,
                effective_total_count,
            )

        class_counts = _build_generation_counts(effective_total_count)
        generation_result = append_cron_generation_batch(class_counts=class_counts)
        generated_total_count = generation_result.inserted_total
        logger.info(
            "Generated %d template-backed external DB row(s) before SQL cron: %s",
            generated_total_count,
            generation_result.inserted_by_class,
        )

    service = LegacyDbIngestionService(
        snapshot_prefix=settings.database_historical_snapshot_prefix
    )

    async with session_factory() as session:
        result = await service.run(
            session,
            trigger_mode="scheduled",
            since_date=last_known_date,
        )

    if result.raw_record_count > 0:
        # Update watermark in PipelineState
        now = datetime.now(timezone.utc)
        async with session_factory() as session:
            stmt = select(PipelineState).where(
                PipelineState.pipeline_name == pipeline_name
            )
            row = await session.scalar(stmt)
            if row is None:
                row = PipelineState(
                    pipeline_name=pipeline_name,
                    state_data={
                        "last_created_at": now.strftime("%Y-%m-%d %H:%M:%S.%f"),
                        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S.%f"),
                    },
                )
                session.add(row)
            else:
                row.state_data = {
                    **row.state_data,
                    "last_created_at": now.strftime("%Y-%m-%d %H:%M:%S.%f"),
                    "updated_at": now.strftime("%Y-%m-%d %H:%M:%S.%f"),
                }
            await session.commit()
        logger.info(
            "Pipeline state updated with new watermark: %s",
            now.strftime("%Y-%m-%d %H:%M:%S.%f"),
        )

    logger.info("--- SQL Cron Summary ---")
    logger.info(result.log_message or "DB ingestion completed")
    logger.info("Raw Object Count: %d", result.raw_object_count)
    logger.info("New Records:      %d", result.raw_record_count)
    logger.info("Skipped (dupes):  %d", result.skipped_count)
    logger.info("Total Extracted:  %d", result.total_extracted_count)
    logger.info("Generated Delta:  %d", generated_total_count)
    if result.snapshot_storage_uri:
        logger.info("R2 Snapshot URI:  %s", result.snapshot_storage_uri)

    await engine.dispose()


async def main() -> None:
    _r2_prefix = os.environ["SICURRE_DATABASE_HISTORICAL_SNAPSHOT_PREFIX"]
    logger.info("Starting SQL cron (R2 target: %s)", _r2_prefix)
    await run_incremental_sql_cron()


if __name__ == "__main__":
    asyncio.run(main())
