from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.external_db_seed import seed_external_database  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed the standalone historical external database with synthetic and adapted data"
    )
    parser.parse_args()
    seed_external_database()
