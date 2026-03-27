from __future__ import annotations

import asyncio
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = BACKEND_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.database import AsyncSessionFactory
from storage.services import CertFRIngestionService


async def main() -> None:
    service = CertFRIngestionService()

    async with AsyncSessionFactory() as session:
        result = await service.run(session, trigger_mode="scheduled")

    print(
        "CERT-FR ingestion completed:",
        f"run={result.ingestion_run_id}",
        f"source={result.source_system_id}",
        f"raw_objects={result.raw_object_count}",
        f"raw_records={result.raw_record_count}",
        f"snapshot={result.snapshot_storage_uri}",
    )


if __name__ == "__main__":
    asyncio.run(main())
