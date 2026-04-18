from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.database import AsyncSessionFactory  # noqa: E402
from data_platform.extractors.certfr_cti import CertFRCtiExtractor  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run CERT-FR CTI ingestion.")
    parser.add_argument(
        "--trigger",
        type=str,
        default="scheduled",
        choices=["scheduled", "manual"],
        help="The trigger mode for the ingestion run.",
    )
    parser.add_argument(
        "--historical",
        action="store_true",
        help="Crawl the full paginated CTI/IOC indexes instead of the capped scheduled scan.",
    )
    args = parser.parse_args()

    service = CertFRCtiExtractor()

    async with AsyncSessionFactory() as session:
        result = await service.run(
            session,
            trigger_mode=args.trigger,
            fetch_historical=args.historical,
        )

    print(f"CERT-FR CTI ingestion completed (Historical={args.historical}):")
    print(f"  Run ID           : {result.ingestion_run_id}")
    print(f"  Source System ID : {result.source_system_id}")
    print(f"  Discovered       : {result.discovered_count}")
    print(f"  New (Pending)    : {result.new_count}")
    print(f"  Extracted        : {result.extracted_count}")
    print(f"  Skipped          : {result.skipped_count}")
    print(f"  Failed           : {result.failed_count}")


if __name__ == "__main__":
    asyncio.run(main())
