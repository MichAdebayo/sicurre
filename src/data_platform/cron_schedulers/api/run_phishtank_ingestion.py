"""Run the scheduled PhishTank ingestion delegate incrementally.

This orchestrator:
1. Retrieves the maximum submission_time (watermark) currently in the DB.
2. Fetches the live feed from PhishTank.
3. Filters the live feed to only include entries newer than the watermark.
4. Writes the filtered delta CSV to R2 under cron/api/phishtank/<timestamp>/.
5. Triggers the offline CLI ingestion workflow using a local temp copy.
"""

from __future__ import annotations

import asyncio
import csv
import logging
import os
import sys
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

# Force snapshot storage to R2 under the cron/api/phishtank prefix
os.environ["SICURRE_PHISHTANK_SNAPSHOT_STORAGE_BACKEND"] = "prod"
os.environ["SICURRE_PHISHTANK_SNAPSHOT_PREFIX"] = "cron/api/phishtank"

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import get_settings
from core.database import Base
from data_platform.extractors.phishtank import (
    PHISHTANK_CSV_FIELDS,
    PhishTankFeedClient,
    PhishTankFetchedPayload,
    PhishTankIngestionService,
)
from data_platform.services.shared.snapshot_storage import build_snapshot_store
from data_platform.services.shared.watermark import WatermarkService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def _build_csv_payload(
    *,
    entries: list[dict[str, str]],
    fieldnames: list[str],
    csv_bytes: bytes,
    source_url: str,
) -> PhishTankFetchedPayload:
    return PhishTankFetchedPayload(
        entries=entries,
        snapshot_bytes=csv_bytes,
        source_url=source_url,
        content_type="text/csv",
        source_format="csv",
    )


async def run_incremental_phishtank_cron() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.data_platform_database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
    new_entries = [
        entry
        for entry in payload.entries
        if str(entry.get("submission_time", "")) > last_known_date
    ]

    logger.info("Delta calculation: %d new entries beyond watermark.", len(new_entries))

    if not new_entries:
        logger.info("No new entries found since watermark. Cron exiting cleanly.")
        await engine.dispose()
        return

    # Build the delta CSV content in memory
    now = datetime.now(timezone.utc)
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")

    fieldnames = [
        *PHISHTANK_CSV_FIELDS,
        *sorted(
            {
                key
                for entry in new_entries
                for key in entry
                if key not in PHISHTANK_CSV_FIELDS
            }
        ),
    ]

    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for entry in new_entries:
        writer.writerow({field: entry.get(field, "") for field in fieldnames})
    csv_bytes = buf.getvalue().encode("utf-8")

    # Write the delta CSV to R2 via the snapshot store
    snapshot_store = build_snapshot_store(
        local_root_dir=ROOT_DIR / "data",
        repo_root=ROOT_DIR,
        source_key="phishtank",
    )
    object_key = snapshot_store.build_object_key(
        source_prefix=f"cron/api/phishtank/{timestamp_str}",
        filename="phishtank_delta.csv",
    )
    result = await snapshot_store.write_snapshot(
        object_key=object_key,
        payload=csv_bytes,
        content_type="text/csv",
    )
    logger.info("Delta CSV uploaded to: %s", result.storage_uri)

    payload_for_ingestion = _build_csv_payload(
        entries=new_entries,
        fieldnames=fieldnames,
        csv_bytes=csv_bytes,
        source_url=result.storage_uri,
    )

    async def fetch_entries() -> PhishTankFetchedPayload:
        return payload_for_ingestion

    service = PhishTankIngestionService(fetch_entries=fetch_entries)
    async with session_factory() as session:
        await service.run(session, trigger_mode="scheduled")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_incremental_phishtank_cron())
