"""Poll the recurring R2 file prefixes and ingest new CSV/TXT files."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.extractors.file_dropzone import run_cron_file_ingestion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Starting file cron (R2 inputs: cron/file/csv + cron/file/txt)")
    result = await run_cron_file_ingestion(trigger_mode="scheduled")
    logger.info(
        "File cron complete: processed=%d inserted=%d skipped=%d",
        result.processed_files,
        result.inserted_records,
        result.skipped_files,
    )


if __name__ == "__main__":
    asyncio.run(main())
