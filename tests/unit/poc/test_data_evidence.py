"""Tests for isolated, read-only POC data evidence access."""

import sqlite3
from pathlib import Path

import pytest

from poc.data_evidence import PocDataEvidenceStore


def test_evidence_store_is_lazy_and_reads_local_counts(tmp_path: Path) -> None:
    """The store opens no engine until queried and reads only its injected path."""
    database_path = tmp_path / "evidence.db"
    store = PocDataEvidenceStore(database_path)
    assert store._engine is None

    connection = sqlite3.connect(database_path)
    connection.execute("CREATE TABLE data_raw_record (id INTEGER PRIMARY KEY)")
    connection.executemany("INSERT INTO data_raw_record (id) VALUES (?)", [(1,), (2,)])
    connection.commit()
    connection.close()

    assert store.table_exists("data_raw_record")
    assert store.count("data_raw_record") == 2
    assert store.query("SELECT id FROM data_raw_record ORDER BY id") == [{"id": 1}, {"id": 2}]


def test_evidence_store_handles_absent_tables_and_rejects_identifiers(tmp_path: Path) -> None:
    """Missing evidence is an empty state and identifiers cannot inject SQL."""
    store = PocDataEvidenceStore(tmp_path / "empty.db")
    assert not store.table_exists("missing")
    assert store.query("SELECT * FROM missing") == []
    assert store.count("missing") == 0
    with pytest.raises(ValueError, match="Invalid evidence table name"):
        store.count("data_raw_record; DROP TABLE data_raw_record")
