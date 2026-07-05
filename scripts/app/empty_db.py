#!/usr/bin/env python3
"""Utility script to empty all table contents from the local SQLite database (`sicurre.db`).

This script preserves table schemas, indices, and database migrations while deleting 
all row records and resetting auto-increment sequences, allowing clean end-to-end 
user testing from scratch.

Location: scripts/app/empty_db.py

Usage:
    python scripts/app/empty_db.py
    uv run python scripts/app/empty_db.py
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# Repository root directory
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "local" / "sicurre.db"


def get_all_tables(conn: sqlite3.Connection) -> list[str]:
    """Retrieve all user-defined table names in the SQLite database."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    )
    return [row[0] for row in cursor.fetchall()]


def empty_database(db_path: Path) -> None:
    """Delete all rows from all tables in the target SQLite database."""
    if not db_path.exists():
        print(f"❌ Error: Database file not found at '{db_path}'", file=sys.stderr)
        sys.exit(1)

    print(f"📦 Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Disable foreign keys temporarily for clean deletion order
        cursor.execute("PRAGMA foreign_keys = OFF;")
        
        tables = get_all_tables(conn)
        if not tables:
            print("ℹ️  No user tables found in database.")
            return

        print(f"🧹 Clearing content from {len(tables)} tables...")
        
        cleared_count = 0
        for table in tables:
            cursor.execute(f'DELETE FROM "{table}";')
            cleared_count += 1
            print(f"  ✓ Cleared table: {table}")

        # Reset auto-increment counters if sqlite_sequence exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence';"
        )
        if cursor.fetchone():
            cursor.execute("DELETE FROM sqlite_sequence;")
            print("  ✓ Reset sqlite_sequence auto-increment counters")

        conn.commit()

        # Re-enable foreign keys and reclaim disk space
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("VACUUM;")
        print("  ✓ Ran VACUUM optimization")

        print("\n🔍 Verification (row counts post-clearing):")
        for table in tables:
            cursor.execute(f'SELECT COUNT(*) FROM "{table}";')
            count = cursor.fetchone()[0]
            status = "ZERO" if count == 0 else f"⚠️ {count}"
            print(f"  • {table:<30}: {status}")

        print("\n✅ Successfully emptied all table content from sicurre.db!")

    except sqlite3.Error as err:
        conn.rollback()
        print(f"\n❌ Database error occurred: {err}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Utility script to empty all table contents from sicurre.db"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to sicurre.db SQLite database file (default: data/local/sicurre.db)",
    )
    args = parser.parse_args()

    empty_database(args.db_path)


if __name__ == "__main__":
    main()
