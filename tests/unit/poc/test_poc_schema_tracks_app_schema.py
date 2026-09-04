"""The POC's hand-rolled schema tracks the application's."""

from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import pytest

from poc import local_runtime

#: Columns the application records that the POC must also carry.
_REQUIRED = ("model_version", "model_revision")


@pytest.fixture(autouse=True)
def _poc_seed_credentials(monkeypatch):
    """`ensure_local_auth_db` refuses to run without the POC seed passwords."""
    monkeypatch.setattr(local_runtime, "DEFAULT_ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setattr(local_runtime, "DEFAULT_VIEWER_PASSWORD", "test-viewer-password")


def _bootstrap(path: Path) -> list[str]:
    local_runtime.POC_AUTH_DB_PATH = path
    local_runtime.ensure_local_auth_db()
    with sqlite3.connect(str(path)) as conn:
        return [row[1] for row in conn.execute("PRAGMA table_info(app_inference_event)")]


def test_a_fresh_poc_database_has_the_model_identity_columns(tmp_path) -> None:
    columns = _bootstrap(tmp_path / "fresh.db")
    for name in _REQUIRED:
        assert name in columns, f"a fresh POC database is missing {name}"


def test_an_existing_poc_database_heals_instead_of_needing_deletion(tmp_path) -> None:
    """The path that matters: someone already has a POC database with data."""
    path = tmp_path / "existing.db"
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            "CREATE TABLE app_inference_event ("
            "id TEXT PRIMARY KEY, created_at TEXT NOT NULL, user_email TEXT NOT NULL,"
            "context TEXT NOT NULL, subject TEXT NOT NULL, sender TEXT NOT NULL,"
            "snippet TEXT NOT NULL, safety_verdict TEXT NOT NULL,"
            "label_verdict TEXT NOT NULL, composite_score REAL NOT NULL,"
            "is_phishing INTEGER NOT NULL, delivered_in_smail INTEGER NOT NULL,"
            "llm_provider TEXT NOT NULL, explanation TEXT NOT NULL,"
            "stage_scores_json TEXT NOT NULL, stage_labels_json TEXT NOT NULL,"
            "stage_breakdown_json TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO app_inference_event VALUES"
            "('e1','2026-09-04','a@b.test','poc','s','f@g.test','x','safe',"
            "'legitimate',0.1,0,1,'','',  '{}','{}','{}')"
        )

    columns = _bootstrap(path)
    for name in _REQUIRED:
        assert name in columns, f"an existing POC database did not gain {name}"

    with sqlite3.connect(str(path)) as conn:
        surviving = conn.execute("SELECT count(*) FROM app_inference_event").fetchone()[0]
    assert surviving == 1, "healing the schema must not discard existing rows"


def test_bootstrapping_twice_is_a_no_op(tmp_path) -> None:
    """A duplicate-column error on second start would break every demo."""
    path = tmp_path / "twice.db"
    _bootstrap(path)
    _bootstrap(path)  # must not raise


@pytest.mark.parametrize("column", _REQUIRED)
def test_each_column_is_declared_in_both_create_and_alter(column: str) -> None:
    """Both halves must exist, or one of the two database states is broken."""
    source = inspect.getsource(local_runtime)
    create_block = source[source.index("CREATE TABLE IF NOT EXISTS app_inference_event") :]
    create_block = create_block[: create_block.index('"""')]

    assert column in create_block, f"{column} missing from the CREATE (fresh databases)"
    assert f'ADD COLUMN {column}' in source, f"{column} has no ALTER (existing databases)"
