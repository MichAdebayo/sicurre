"""Run the scheduled PhishTank ingestion delegate."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.cli.ingest.phishtank import run_ingestion


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the scheduled PhishTank ingestion delegate."
    )
    return parser.parse_args()


if __name__ == "__main__":
    parse_args()
    asyncio.run(run_ingestion(trigger_mode="scheduled"))
