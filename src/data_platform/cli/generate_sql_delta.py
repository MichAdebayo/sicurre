"""CLI tool to generate a synthetic delta in the external threats DB.
Usage: uv run python src/data_platform/cli/generate_sql_delta.py [n]
"""

import argparse
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))

from data_platform.services.database.seed import append_to_database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic threats to external DB.")
    parser.add_argument("-n", "--count", type=int, default=100, help="Number of threats to append")
    args = parser.parse_args()

    logger.info(f"Generating {args.count} synthetic threats for external DB...")
    inserted = append_to_database(args.count)
    logger.info(f"Successfully generated {inserted} new synthetic threats.")

if __name__ == "__main__":
    main()
