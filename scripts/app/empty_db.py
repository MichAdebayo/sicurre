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
import logging
import sqlite3
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("empty_db")

# Repository root directory
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "local" / "sicurre.db"


def format_size(size_bytes: int) -> str:
    """Format byte count into human-readable string (KB/MB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def get_all_tables(conn: sqlite3.Connection) -> list[str]:
    """Retrieve all user-defined table names in the SQLite database."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    )
    return [row[0] for row in cursor.fetchall()]


def get_table_row_count(conn: sqlite3.Connection, table_name: str) -> int:
    """Return the total number of rows in a given table."""
    cursor = conn.cursor()
    cursor.execute(f'SELECT COUNT(*) FROM "{table_name}";')
    return cursor.fetchone()[0]


def empty_database(db_path: Path) -> None:
    """Delete all rows from all tables in the target SQLite database."""
    if not db_path.exists():
        logger.error("Database file not found at path: %s", db_path)
        sys.exit(1)

    initial_file_size = db_path.stat().st_size
    logger.info("Connecting to SQLite database: %s", db_path)
    logger.info("Initial database file size: %s", format_size(initial_file_size))

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        logger.info("Disabling foreign key constraints for bulk truncation...")
        cursor.execute("PRAGMA foreign_keys = OFF;")
        
        tables = get_all_tables(conn)
        if not tables:
            logger.warning("No user tables found in database.")
            return

        logger.info("Found %d user-defined tables to clear:", len(tables))

        total_rows_deleted = 0
        table_stats: list[tuple[str, int]] = []

        # Step 1: Pre-scan row counts
        for table in tables:
            row_count = get_table_row_count(conn, table)
            table_stats.append((table, row_count))
            logger.info("  • Table '%s': %d rows currently present", table, row_count)

        # Step 2: Delete records
        logger.info("Executing DELETE queries on all tables...")
        for table, initial_count in table_stats:
            cursor.execute(f'DELETE FROM "{table}";')
            total_rows_deleted += initial_count
            logger.info("  ✓ Cleared table '%s' (%d rows deleted)", table, initial_count)

        # Step 3: Reset auto-increment sequence counters if sqlite_sequence exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence';"
        )
        if cursor.fetchone():
            cursor.execute("DELETE FROM sqlite_sequence;")
            logger.info("  ✓ Reset sqlite_sequence auto-increment counters")

        # Step 4: Commit changes
        logger.info("Committing transaction...")
        conn.commit()

        # Step 5: Re-enable foreign keys and run VACUUM
        logger.info("Re-enabling foreign key constraints...")
        cursor.execute("PRAGMA foreign_keys = ON;")
        
        logger.info("Running VACUUM to reclaim unallocated disk space...")
        cursor.execute("VACUUM;")

        final_file_size = db_path.stat().st_size
        saved_bytes = initial_file_size - final_file_size
        logger.info("VACUUM complete. Final database size: %s (reclaimed %s)", 
                    format_size(final_file_size), format_size(max(0, saved_bytes)))

        # Step 6: Post-clearing verification pass
        logger.info("Executing post-clearing verification pass...")
        verification_passed = True
        for table in tables:
            count = get_table_row_count(conn, table)
            if count == 0:
                logger.info("  ✓ Verified '%s': 0 rows remaining", table)
            else:
                logger.error("  ❌ Verification failed for '%s': %d rows remain!", table, count)
                verification_passed = False

        if verification_passed:
            logger.info("==================================================")
            logger.info("SUCCESS: Emptied %d tables (%d total rows deleted)", 
                        len(tables), total_rows_deleted)
            logger.info("sicurre.db is now completely clean and ready for scratch testing!")
            logger.info("==================================================")
        else:
            logger.error("WARNING: Some tables still contain row data post-clearing.")

    except sqlite3.Error as err:
        conn.rollback()
        logger.error("Database operation failed with error: %s", err, exc_info=True)
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
