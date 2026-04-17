from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.external_db_seed import (  # noqa: E402
    append_to_database,
    seed_external_database,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed or incrementally extend the standalone external historical database."
    )
    parser.add_argument(
        "--append-n",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Append N new synthetic phishing rows to an existing DB "
            "without deleting existing data.  "
            "Use --db-url to target a specific DB file."
        ),
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        metavar="URL",
        help=(
            "SQLAlchemy sync URL for the target DB when using --append-n "
            "(e.g. sqlite:////absolute/path/to/external_threats_cron_test.db). "
            "Defaults to the module-level DB_URL (data/raw/db/external_threats.db)."
        ),
    )
    args = parser.parse_args()

    if args.append_n is not None:
        inserted = append_to_database(args.append_n, db_url=args.db_url)
        print(f"Inserted {inserted} new rows.")
    else:
        seed_external_database()
