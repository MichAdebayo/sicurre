"""Idempotency preflight for local POC dataset previews."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from poc.config import get_poc_settings

NO_CHANGE_EXIT_CODE = 3


def dataset_membership_changed(database_path: Path) -> bool:
    """Return whether eligible normalized messages differ from the latest dataset."""
    with sqlite3.connect(database_path) as connection:
        latest = connection.execute(
            "SELECT id FROM data_dataset ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if latest is None:
            return True
        eligible = {
            str(row[0]).replace("-", "").lower()
            for row in connection.execute(
                """
                WITH ranked AS (
                    SELECT normalized_message_id, label,
                           ROW_NUMBER() OVER (
                               PARTITION BY normalized_message_id
                               ORDER BY annotated_at DESC, created_at DESC, id DESC
                           ) AS annotation_rank
                    FROM data_annotation
                )
                SELECT normalized_message_id
                FROM ranked
                WHERE annotation_rank = 1
                  AND label IN ('phishing', 'spam', 'legitimate')
                """
            )
        }
        current = {
            str(row[0]).replace("-", "").lower()
            for row in connection.execute(
                "SELECT normalized_message_id FROM data_dataset_item WHERE dataset_id = ?",
                (latest[0],),
            )
        }
    return eligible != current


def main() -> None:
    """Exit with a distinct no-change code for Make orchestration."""
    database_path = get_poc_settings().data_platform_database_path
    if dataset_membership_changed(database_path):
        print("POC preview required: eligible membership changed.")
        return
    print("POC preview skipped: latest dataset already contains every eligible message.")
    raise SystemExit(NO_CHANGE_EXIT_CODE)


if __name__ == "__main__":
    main()
