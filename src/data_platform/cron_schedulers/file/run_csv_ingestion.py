"""Run the scheduled CSV ingestion delegate.

Forces R2 storage under cron/files/csv/ prefix.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# Force snapshot storage to R2 under the cron/files/csv prefix
os.environ["SICURRE_RAW_SNAPSHOT_STORAGE_BACKEND"] = "prod"

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.cli.ingest.file.csv_ingestion import run_ingestion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    logger.info("Starting CSV file cron (R2 target: cron/files/csv)")
    asyncio.run(run_ingestion("data/raw/file/csv", trigger_mode="scheduled"))
