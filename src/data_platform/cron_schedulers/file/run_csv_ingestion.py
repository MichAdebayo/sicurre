"""Run the scheduled CSV ingestion delegate."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.cli.ingest.file.csv_ingestion import run_ingestion


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest static CSV datasets.")
    parser.add_argument(
        "--dir",
        type=str,
        default="data/raw/csv",
        help="Directory to recursively search for CSV files.",
    )
    args = parser.parse_args()
    asyncio.run(run_ingestion(args.dir))
