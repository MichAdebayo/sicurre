"""Tests for isolated POC authentication and remembered sessions."""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import bcrypt

from poc.authentication import PocAuthStore


def build_auth_store(database_path: Path) -> PocAuthStore:
    """Create the minimum local auth schema used by the store."""
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE poc_user (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            last_login_at TEXT,
            session_token_hash TEXT,
            session_expires_at TEXT
        )
        """
    )
    password_hash = bcrypt.hashpw(b"correct-password", bcrypt.gensalt()).decode()
    connection.execute(
        "INSERT INTO poc_user (id, email, password_hash, display_name, role) "
        "VALUES (?, ?, ?, ?, ?)",
        ("user-1", "admin@example.test", password_hash, "Admin", "admin"),
    )
    connection.commit()
    connection.close()
    return PocAuthStore(database_path)


def test_authentication_normalizes_email_and_rejects_invalid_credentials(
    tmp_path: Path,
) -> None:
    """Authentication succeeds only for a matching normalized credential pair."""
    store = build_auth_store(tmp_path / "auth.db")
    user = store.authenticate(" ADMIN@EXAMPLE.TEST ", "correct-password")
    assert user is not None
    assert user["id"] == "user-1"
    assert store.authenticate("admin@example.test", "wrong") is None
    assert store.authenticate("missing@example.test", "correct-password") is None
    assert not store.password_matches("password", "malformed")


def test_remembered_session_is_hashed_resolved_and_revoked(tmp_path: Path) -> None:
    """Remembered sessions persist no plaintext token and honor expiry."""
    store = build_auth_store(tmp_path / "auth.db")
    now = datetime(2026, 7, 14, 12, tzinfo=UTC)
    session_id = store.create_session("user-1", now=now)

    row = store.query(
        "SELECT session_token_hash, session_expires_at FROM poc_user WHERE id = ?",
        ("user-1",),
    )[0]
    assert row["session_token_hash"] != session_id
    assert store.resolve_session(session_id, now=now) is not None
    assert store.resolve_session(session_id, now=now + timedelta(days=8)) is None

    store.revoke_session("user-1")
    assert store.resolve_session(session_id, now=now) is None


def test_record_login_updates_auditable_timestamp(tmp_path: Path) -> None:
    """Successful authentication updates the local evidence timestamp."""
    store = build_auth_store(tmp_path / "auth.db")
    now = datetime(2026, 7, 14, 12, tzinfo=UTC)
    store.record_login("user-1", now=now)
    row = store.query("SELECT last_login_at FROM poc_user WHERE id = ?", ("user-1",))[0]
    assert row["last_login_at"] == now.isoformat()
