from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.processed_exports import (
    ProcessedExportsService,
)  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Merge processed CSVs into train/val/test splits"
    )
    parser.add_argument(
        "--downsample-to",
        "-d",
        type=int,
        default=0,
        help="Cap each class at this many rows (0 = no cap)",
    )
    args = parser.parse_args()
    ProcessedExportsService().build_dataset_splits(args.downsample_to)
