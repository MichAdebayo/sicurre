"""Poll the recurring R2 file prefixes and ingest new CSV/TXT files.

Pass --reserved to poll cron/reserved/file/{csv,txt} instead of cron/file/{csv,txt}.
"""

from __future__ import annotations

import argparse as _argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# ── Reserved-slot routing (must happen before file_dropzone import) ───────────
_parser = _argparse.ArgumentParser(add_help=False)
_parser.add_argument("--reserved", action="store_true", default=False)
_reserved_args, _ = _parser.parse_known_args()

if _reserved_args.reserved:
    os.environ["SICURRE_FILE_CRON_CSV_PREFIX"] = "raw-snapshots/cron/reserved/file/csv"
    os.environ["SICURRE_FILE_CRON_TXT_PREFIX"] = "raw-snapshots/cron/reserved/file/txt"
# ─────────────────────────────────────────────────────────────────────────────

from data_platform.extractors.file_dropzone import run_cron_file_ingestion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    from data_platform.extractors.file_dropzone import (
        CRON_FILE_CSV_PREFIX,
        CRON_FILE_TXT_PREFIX,
    )

    logger.info(
        "Starting file cron (R2 inputs: %s + %s)",
        CRON_FILE_CSV_PREFIX,
        CRON_FILE_TXT_PREFIX,
    )
    result = await run_cron_file_ingestion(trigger_mode="scheduled")
    logger.info(
        "File cron complete: processed=%d inserted=%d skipped=%d",
        result.processed_files,
        result.inserted_records,
        result.skipped_files,
    )


if __name__ == "__main__":
    asyncio.run(main())
