"""Run the PhishTank ingestion job.

Usage::

    # From live feed
    uv run --group backend python backend/scripts/run_phishtank_ingestion.py --trigger manual

    # From existing CSV (when feed is rate-limited)
    uv run --group backend python backend/scripts/run_phishtank_ingestion.py \\
        --trigger manual --csv data/raw/api/phishtank/phishing-tank.csv

Designed to be called daily by a scheduler (cron / Cloud Scheduler).
Pass ``--trigger manual`` for the first run.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = BACKEND_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import get_settings  # noqa: E402
from core.database import Base  # noqa: E402
from storage.services import (  # noqa: E402
    PhishTankIngestionService,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def _load_csv_entries(csv_path: Path) -> list[dict[str, Any]]:
    """Load PhishTank entries from a CSV file.

    Maps CSV column names to the JSON field names the service expects.
    """
    entries: list[dict[str, Any]] = []
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append({
                "phish_id": row.get("phish_id", ""),
                "url": row.get("url", ""),
                "phish_detail_url": row.get("phish_detail_url", ""),
                "submission_time": row.get("submission_time", ""),
                "verified": row.get("verified", ""),
                "verification_time": row.get("verification_time", ""),
                "online": row.get("online", ""),
                "target": row.get("target", ""),
            })
    return entries


async def main(trigger_mode: str = "scheduled", csv_path: str | None = None) -> None:
    settings = get_settings()
    db_url = settings.database_url
    logger.info("Using database: %s", db_url)

    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Tables ensured")

    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession,
    )

    # Build the service — optionally with a CSV-based fetch function
    if csv_path:
        csv_file = Path(csv_path)
        if not csv_file.exists():
            logger.error("CSV file not found: %s", csv_file)
            sys.exit(1)

        csv_entries = _load_csv_entries(csv_file)
        logger.info(
            "Loaded %d entries from CSV: %s", len(csv_entries), csv_file.name,
        )

        async def fetch_from_csv() -> list[dict[str, Any]]:
            return csv_entries

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PhishTank ingestion")
    parser.add_argument(
        "--trigger", default="scheduled", choices=["manual", "scheduled"],
        help="Trigger mode (default: scheduled)",
    )
    parser.add_argument(
        "--csv", default=None,
        help="Path to a local CSV file to ingest instead of the live feed",
    )
    args = parser.parse_args()
    asyncio.run(main(trigger_mode=args.trigger, csv_path=args.csv))
