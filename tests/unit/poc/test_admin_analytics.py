"""Tests for content-free aggregate POC administration evidence."""

import sqlite3
from pathlib import Path

from poc.admin_analytics import PocAdminAnalytics
from poc.authentication import PocAuthStore
from poc.data_evidence import PocDataEvidenceStore


def _seed_auth_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE poc_user (
            id TEXT PRIMARY KEY, email TEXT, display_name TEXT, role TEXT,
            last_login_at TEXT
        );
        CREATE TABLE app_inference_event (
            id TEXT PRIMARY KEY, user_email TEXT, safety_verdict TEXT,
            label_verdict TEXT, override_verdict TEXT, overridden_at TEXT
        );
        INSERT INTO poc_user VALUES
            ('admin', 'admin@example.test', 'Admin', 'admin', '2026-08-28T08:00:00Z'),
            ('viewer', 'viewer@example.test', 'Viewer', 'viewer', NULL);
        INSERT INTO app_inference_event VALUES
            ('e1', 'admin@example.test', 'safe', 'legitimate', NULL, NULL),
            ('e2', 'admin@example.test', 'safe', 'spam', NULL, NULL),
            ('e3', 'viewer@example.test', 'phishing', 'phishing', NULL, NULL),
            ('e4', 'viewer@example.test', 'phishing', 'phishing', 'safe', '2026-08-28');
        """
    )
    connection.commit()
    connection.close()


def _seed_data_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE data_raw_record (id TEXT PRIMARY KEY);
        CREATE TABLE data_normalized_message (id TEXT PRIMARY KEY);
        CREATE TABLE data_dataset (
            id TEXT PRIMARY KEY, version_tag TEXT, status TEXT, created_at TEXT
        );
        CREATE TABLE data_dataset_item (id TEXT PRIMARY KEY, dataset_id TEXT);
        CREATE TABLE data_ingestion_run (
            id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, status TEXT
        );
        INSERT INTO data_raw_record VALUES ('r1'), ('r2'), ('r3');
        INSERT INTO data_normalized_message VALUES ('n1'), ('n2');
        INSERT INTO data_dataset VALUES ('d1', 'base-v1', 'frozen', '2026-08-28T08:00:00Z');
        INSERT INTO data_dataset_item VALUES ('i1', 'd1'), ('i2', 'd1');
        INSERT INTO data_ingestion_run VALUES (
            'run-1', '2026-08-28T07:00:00Z', NULL, 'running'
        );
        """
    )
    connection.commit()
    connection.close()


def test_admin_snapshot_aggregates_accounts_classes_and_data_without_content(
    tmp_path: Path,
) -> None:
    """The admin read model exposes bounded aggregates at the intended grains."""
    auth_path = tmp_path / "auth.db"
    data_path = tmp_path / "data.db"
    _seed_auth_database(auth_path)
    _seed_data_database(data_path)

    snapshot = PocAdminAnalytics(
        PocAuthStore(auth_path), PocDataEvidenceStore(data_path)
    ).snapshot()

    assert [(account.role, account.event_count) for account in snapshot.accounts] == [
        ("admin", 2),
        ("viewer", 2),
    ]
    assert snapshot.classifications.total == 4
    assert snapshot.classifications.legitimate == 2
    assert snapshot.classifications.spam == 1
    assert snapshot.classifications.phishing == 1
    assert snapshot.classifications.corrections == 1
    assert snapshot.data_platform.raw_records == 3
    assert snapshot.data_platform.normalized_messages == 2
    assert snapshot.data_platform.dataset_items == 2
    assert snapshot.data_platform.dataset_version == "base-v1"
    assert snapshot.data_platform.latest_ingestion_at == "2026-08-28T07:00:00Z"
    assert snapshot.data_platform.latest_ingestion_status == "running"


def test_admin_analytics_tolerates_missing_ingestion_table(tmp_path: Path) -> None:
    """A fresh local data store has no ingestion evidence yet."""
    analytics = PocAdminAnalytics(
        PocAuthStore(tmp_path / "auth.db"),
        PocDataEvidenceStore(tmp_path / "data.db"),
    )

    assert analytics._latest_ingestion() == {}
