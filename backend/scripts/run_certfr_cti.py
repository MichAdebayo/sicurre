import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = BACKEND_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sicurre_api.core.database import AsyncSessionFactory
from sicurre_api.domains.data_platform.services.certfr_cti import CertFRCtiExtractor


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
        help="Scrape the paginated HTML indexes to discover all historical CTI/IOC reports instead of using the RSS feed.",
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
