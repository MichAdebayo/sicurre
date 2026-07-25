"""Legacy SQLite runtime schema upgrade tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from data_platform.api import auth


def test_legacy_quarantine_table_receives_current_storage_columns(
    tmp_path: Path, monkeypatch
) -> None:
    """Upgrade an existing pre-storage quarantine table without data loss."""
    database_path = tmp_path / "legacy-runtime.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE app_quarantine_item (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                subject TEXT NOT NULL,
                body_text TEXT NOT NULL,
                safety_verdict TEXT NOT NULL,
                composite_score REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'held',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )

    monkeypatch.setattr(auth, "_db_path", lambda: str(database_path))
    auth._ensure_legacy_sqlite_tables()

    with sqlite3.connect(database_path) as connection:
        columns = auth._table_columns(connection, "app_quarantine_item")
        reported_columns = auth._table_columns(connection, "app_reported_email")
        reported_indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list(app_reported_email)").fetchall()
        }

    assert {
        "raw_storage_uri",
        "raw_content_hash",
        "raw_size_bytes",
        "delivery_message_id",
        "delivered_at",
        "last_delivery_error",
    } <= columns
    assert {
        "id",
        "workspace_id",
        "workspace_member_user_id",
        "storage_uri",
        "content_hash",
        "size_bytes",
        "status",
        "received_at",
    } == reported_columns
    assert "ix_app_reported_email_workspace_id" in reported_indexes
