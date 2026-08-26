"""Tests for idempotent local POC dataset previews."""

import sqlite3
from pathlib import Path

import pytest

from poc import release_preflight
from poc.release_preflight import dataset_membership_changed


def _database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE data_dataset (id TEXT PRIMARY KEY, created_at TEXT);
        CREATE TABLE data_dataset_item (dataset_id TEXT, normalized_message_id TEXT);
        CREATE TABLE data_annotation (
            id TEXT, normalized_message_id TEXT, label TEXT,
            annotated_at TEXT, created_at TEXT
        );
        """
    )
    return connection


def test_preflight_requires_first_or_changed_dataset(tmp_path: Path) -> None:
    path = tmp_path / "data.db"
    connection = _database(path)
    connection.execute("INSERT INTO data_annotation VALUES ('a1', 'm1', 'phishing', '1', '1')")
    connection.commit()
    assert dataset_membership_changed(path)

    connection.execute("INSERT INTO data_dataset VALUES ('d1', '1')")
    connection.execute("INSERT INTO data_dataset_item VALUES ('d1', 'm1')")
    connection.commit()
    assert not dataset_membership_changed(path)

    connection.execute("INSERT INTO data_annotation VALUES ('a2', 'm2', 'spam', '2', '2')")
    connection.commit()
    connection.close()
    assert dataset_membership_changed(path)


def test_main_reports_changed_and_unchanged_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "data.db"
    monkeypatch.setattr(
        release_preflight,
        "get_poc_settings",
        lambda: type("Settings", (), {"data_platform_database_path": path})(),
    )
    monkeypatch.setattr(release_preflight, "dataset_membership_changed", lambda _: True)
    release_preflight.main()
    assert "preview required" in capsys.readouterr().out

    monkeypatch.setattr(release_preflight, "dataset_membership_changed", lambda _: False)
    with pytest.raises(SystemExit) as error:
        release_preflight.main()
    assert error.value.code == release_preflight.NO_CHANGE_EXIT_CODE


def test_module_entrypoint_calls_main(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[bool] = []
    monkeypatch.setattr(release_preflight, "main", lambda: called.append(True))
    assert callable(release_preflight.main)
