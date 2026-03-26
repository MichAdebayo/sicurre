"""Run the PhishTank ingestion job.

Usage::

    cd backend && uv run --group backend python scripts/run_phishtank_ingestion.py

Designed to be called daily by a scheduler (cron / Cloud Scheduler).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = BACKEND_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sicurre_api.core.database import AsyncSessionFactory
from sicurre_api.domains.data_platform.services import PhishTankIngestionService


async def main() -> None:
    service = PhishTankIngestionService()

    async with AsyncSessionFactory() as session:
        result = await service.run(session, trigger_mode="scheduled")

    print(result.log_message or "PhishTank ingestion completed")
    print(
        f"  new={result.raw_record_count}"
        f"  skipped={result.skipped_count}"
        f"  objects={result.raw_object_count}"
    )
    if result.snapshot_storage_uri:
        print(f"  snapshot={result.snapshot_storage_uri}")


if __name__ == "__main__":
    asyncio.run(main())
