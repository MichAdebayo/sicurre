from __future__ import annotations

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
    ProcessedExportsService().restructure_processed_exports()
