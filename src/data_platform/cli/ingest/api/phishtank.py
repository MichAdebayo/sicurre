from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[5]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.config import get_settings  # noqa: E402
from core.database import Base  # noqa: E402
from data_platform.extractors.phishtank import (  # noqa: E402
    PhishTankFetchedPayload,
    PhishTankIngestionService,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def _load_csv_payload(csv_path: Path) -> PhishTankFetchedPayload:
    entries: list[dict[str, Any]] = []
    with csv_path.open(encoding="utf-8") as file_handle:
        reader = csv.DictReader(file_handle)
        for row in reader:
            entries.append(
                {
                    "phish_id": row.get("phish_id", ""),
                    "url": row.get("url", ""),
                    "phish_detail_url": row.get("phish_detail_url", ""),
                    "submission_time": row.get("submission_time", ""),
                    "verified": row.get("verified", ""),
                    "verification_time": row.get("verification_time", ""),
                    "online": row.get("online", ""),
                    "target": row.get("target", ""),
                }
            )
    return PhishTankFetchedPayload(
        entries=entries,
        snapshot_bytes=csv_path.read_bytes(),
        source_url=str(csv_path),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PhishTank ingestion")
    parser.add_argument(
        "--trigger",
        default="scheduled",
        choices=["manual", "scheduled"],
        help="Trigger mode (default: scheduled)",
    )
    parser.add_argument(
        "--csv",
        default=None,
        help="Path to a local CSV file to ingest instead of the live feed",
    )
    return parser.parse_args()


async def run_ingestion(
    *,
    trigger_mode: str = "scheduled",
    csv_path: str | None = None,
) -> None:
    settings = get_settings()
    db_url = settings.database_url
    logger.info("Using database: %s", db_url)

    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Tables ensured")

    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    if csv_path:
        csv_file = Path(csv_path)
        if not csv_file.exists():
            logger.error("CSV file not found: %s", csv_file)
            raise SystemExit(1)

        csv_payload = _load_csv_payload(csv_file)
        logger.info(
            "Loaded %d entries from CSV: %s",
            len(csv_payload.entries),
            csv_file.name,
        )

        async def fetch_from_csv() -> PhishTankFetchedPayload:
            return csv_payload

        service = PhishTankIngestionService(fetch_entries=fetch_from_csv)
    else:
        service = PhishTankIngestionService()

    async with session_factory() as session:
        result = await service.run(session, trigger_mode=trigger_mode)

    print(result.log_message or "PhishTank ingestion completed")
    print(
        f"  new={result.raw_record_count}"
        f"  skipped={result.skipped_count}"
        f"  filtered={result.filtered_count}"
        f"  feed={result.total_feed_count}"
        f"  objects={result.raw_object_count}"
    )
    if result.snapshot_storage_uri:
        print(f"  snapshot={result.snapshot_storage_uri}")

    await engine.dispose()


async def main() -> None:
    args = parse_args()
    await run_ingestion(trigger_mode=args.trigger, csv_path=args.csv)


if __name__ == "__main__":
    asyncio.run(main())
