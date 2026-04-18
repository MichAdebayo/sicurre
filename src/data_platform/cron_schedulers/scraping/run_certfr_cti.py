import argparse
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.cli.ingest.scraping.certfr import run_ingestion


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the scheduled CERT-FR CTI ingestion delegate."
    )
    return parser.parse_args()


async def main() -> None:
    parse_args()
    await run_ingestion(trigger_mode="scheduled", fetch_historical=False)


if __name__ == "__main__":
    asyncio.run(main())
