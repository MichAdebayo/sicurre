"""Tests for local POC persistence and credential seeding."""

import sqlite3
from pathlib import Path

import bcrypt
import pytest

from poc import local_runtime


def test_auth_database_is_seeded_idempotently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "nested" / "poc.db"
    monkeypatch.setattr(local_runtime, "POC_AUTH_DB_PATH", database_path)
    monkeypatch.setattr(local_runtime, "DEFAULT_ADMIN_PASSWORD", "admin-password")
    monkeypatch.setattr(local_runtime, "DEFAULT_VIEWER_PASSWORD", "viewer-password")
    monkeypatch.setattr(local_runtime, "DEFAULT_ADMIN_EMAIL", "admin@example.test")
    monkeypatch.setattr(local_runtime, "DEFAULT_VIEWER_EMAIL", "viewer@example.test")

    local_runtime.ensure_local_auth_db()
    local_runtime.ensure_local_auth_db()

    connection = sqlite3.connect(database_path)
    try:
        users = connection.execute(
            "SELECT email, password_hash FROM poc_user ORDER BY email"
        ).fetchall()
        event_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(app_inference_event)")
        }
    finally:
        connection.close()

    assert len(users) == 2
    assert bcrypt.checkpw(b"admin-password", users[0][1].encode())
    assert "override_verdict" in event_columns
    assert "inference_source" in event_columns


def test_missing_passwords_fail_before_database_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "poc.db"
    monkeypatch.setattr(local_runtime, "POC_AUTH_DB_PATH", database_path)
    monkeypatch.setattr(local_runtime, "DEFAULT_ADMIN_PASSWORD", "")
    monkeypatch.setattr(local_runtime, "DEFAULT_VIEWER_PASSWORD", "")

    try:
        local_runtime.ensure_local_auth_db()
    except RuntimeError as exc:
        assert "SICURRE_POC_ADMIN_PASSWORD" in str(exc)
    else:
        raise AssertionError("Missing POC passwords must stop database seeding.")
    assert not database_path.exists()


def test_demo_accounts_do_not_expose_passwords() -> None:
    accounts = local_runtime.demo_accounts()
    assert {account["role"] for account in accounts} == {"Administrateur", "Observateur"}
    assert all("password" not in account for account in accounts)
