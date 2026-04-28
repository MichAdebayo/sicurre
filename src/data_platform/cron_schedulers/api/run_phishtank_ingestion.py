"""Run the scheduled PhishTank ingestion delegate incrementally.

This orchestrator:
1. Retrieves the maximum submission_time (watermark) currently in the DB.
2. Fetches the live feed from PhishTank.
3. Filters the live feed to only include entries newer than the watermark.
4. Saves the filtered delta directly to data/raw-snapshots/cron/phishtank/...
5. Triggers the offline CLI ingestion workflow using the written delta file.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Force the ingestion service to write its snapshot to R2 under the cron/ prefix
os.environ["SICURRE_PHISHTANK_SNAPSHOT_STORAGE_BACKEND"] = "prod"
os.environ["SICURRE_PHISHTANK_SNAPSHOT_PREFIX"] = "cron/phishtank"

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.config import get_settings
from data_platform.cli.ingest.api.phishtank import run_ingestion
from data_platform.extractors.phishtank import PhishTankFeedClient, PHISHTANK_CSV_FIELDS
from data_platform.services.shared.watermark import WatermarkService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the scheduled PhishTank ingestion incrementally."
    )
    return parser.parse_args()


async def run_incremental_phishtank_cron() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    source_name = "phishtank-online-valid"
    
    async with session_factory() as session:
        watermark_str = await WatermarkService.get_max_json_field_date(
            session, source_name, "$.submission_time"
        )
    
    # If no previous data, we assume an old watermark so everything is accepted
    last_known_date = watermark_str or "1970-01-01T00:00:00+00:00"
    logger.info("PhishTank last known submission_time: %s", last_known_date)

    # Fetch live data
    api_key = getattr(settings, "phishtank_api_key", None)
    client = PhishTankFeedClient(api_key=api_key)
    logger.info("Fetching live PhishTank feed...")
    payload = await client.fetch_entries()
    
    total_entries = len(payload.entries)
    logger.info("Fetched %d total entries from live feed.", total_entries)
    
    # Filter for entries strictly newer than the watermark
    # PhishTank dates look like '2026-04-18T16:40:13+00:00'
    new_entries = [
        entry for entry in payload.entries 
        if str(entry.get("submission_time", "")) > last_known_date
    ]
    
    logger.info("Delta calculation: %d new entries beyond watermark.", len(new_entries))
    
    if not new_entries:
        logger.info("No new entries found since watermark. Cron exiting cleanly.")
        await engine.dispose()
        return

    # Write the delta to the cron folder
    now = datetime.now(timezone.utc)
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")
    cron_dir = ROOT_DIR / "data" / "raw-snapshots" / "cron" / "phishtank" / timestamp_str
    cron_dir.mkdir(parents=True, exist_ok=True)
    delta_csv_path = cron_dir / "phishtank_delta.csv"

    fieldnames = [
        *PHISHTANK_CSV_FIELDS,
        *sorted(
            {key for entry in new_entries for key in entry if key not in PHISHTANK_CSV_FIELDS}
        ),
    ]
    
    with delta_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for entry in new_entries:
            writer.writerow({field: entry.get(field, "") for field in fieldnames})
            
    logger.info("Saved incremental delta to: %s", delta_csv_path)

    # Offload the ingestion to the main CLI with the CSV override
    await run_ingestion(trigger_mode="scheduled", csv_path=str(delta_csv_path))

    await engine.dispose()


if __name__ == "__main__":
    parse_args()
    asyncio.run(run_incremental_phishtank_cron())
