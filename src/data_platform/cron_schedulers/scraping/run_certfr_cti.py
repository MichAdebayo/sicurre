"""Run the scheduled CERT-FR CTI ingestion delegate.

Forces R2 storage under cron/scraping/certfr_cti/ prefix.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# Force snapshot storage to R2 under the cron/scraping/certfr_cti prefix
os.environ["SICURRE_CERTFR_SNAPSHOT_STORAGE_BACKEND"] = "prod"
os.environ["SICURRE_CERTFR_SNAPSHOT_PREFIX"] = "cron/scraping/certfr_cti"

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.cli.ingest.scraping.certfr import run_ingestion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Starting CERT-FR CTI cron (R2 target: cron/scraping/certfr_cti)")
    await run_ingestion(trigger_mode="scheduled", fetch_historical=False)


if __name__ == "__main__":
    asyncio.run(main())
