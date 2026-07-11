"""Unit tests for KaggleGateway and write_split_csv."""

from __future__ import annotations

import csv
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from data_platform.services.shared.kaggle_gateway import (
    KaggleGateway,
    KagglePushError,
    write_split_csv,
)


@pytest.fixture
def gateway() -> KaggleGateway:
    return KaggleGateway(username="testuser", key="testkey")


# ── write_split_csv ───────────────────────────────────────────────────────────


def test_write_split_csv_creates_file(tmp_path: Path) -> None:
    dest = tmp_path / "train.csv"
    write_split_csv(
        [{"text": "hello phish", "label": "phishing"}],
        dest,
    )

    assert dest.exists()
    with dest.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["text"] == "hello phish"
    assert rows[0]["label"] == "phishing"


def test_write_split_csv_creates_parent_dirs(tmp_path: Path) -> None:
    dest = tmp_path / "deep" / "nested" / "val.csv"
    write_split_csv([{"text": "ok", "label": "legitimate"}], dest)

    assert dest.exists()


def test_write_split_csv_empty_rows_writes_no_file(tmp_path: Path) -> None:
    dest = tmp_path / "empty.csv"
    write_split_csv([], dest)

    assert not dest.exists()


def test_write_split_csv_multiple_rows(tmp_path: Path) -> None:
    rows = [
        {"text": "spam email", "label": "spam"},
        {"text": "phishing link", "label": "phishing"},
        {"text": "normal newsletter", "label": "legitimate"},
    ]
    dest = tmp_path / "test.csv"
    write_split_csv(rows, dest)

    with dest.open(newline="") as fh:
        reader = list(csv.DictReader(fh))
    assert len(reader) == 3
    assert [r["label"] for r in reader] == ["spam", "phishing", "legitimate"]


# ── KaggleGateway._parse_version_number ──────────────────────────────────────


def test_parse_version_number_returns_version(gateway: KaggleGateway) -> None:
    stdout = "Your dataset has been updated to version 5."
    assert gateway._parse_version_number(stdout) == 5


def test_parse_version_number_fallback_to_zero(gateway: KaggleGateway) -> None:
    assert gateway._parse_version_number("Dataset version is being created.") == 0


def test_parse_version_number_first_numeric_wins(gateway: KaggleGateway) -> None:
    stdout = "version 3\nsome other line version 10"
    assert gateway._parse_version_number(stdout) == 3


def test_push_sync_success(gateway: KaggleGateway, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    monkeypatch.delenv("KAGGLE_KEY", raising=False)
    mock_api = MagicMock()
    mock_api.dataset_create_version.return_value = MagicMock(versionNumber=7)

    gateway._api_factory = lambda: mock_api
    version = gateway._push_sync("user/sicurre-data", tmp_path, "Test message")

    assert version == 7
    mock_api.authenticate.assert_called_once()
    assert os.environ["KAGGLE_API_TOKEN"] == "testkey"
    assert "KAGGLE_KEY" not in os.environ
    mock_api.dataset_create_version.assert_called_once_with(
        folder=str(tmp_path),
        version_notes="Test message",
        quiet=True,
        convert_to_csv=False,
        dir_mode="tar",
    )


def test_push_sync_raises_on_failure(gateway: KaggleGateway, tmp_path: Path) -> None:
    mock_api = MagicMock()
    mock_api.dataset_create_version.side_effect = Exception("API error")

    gateway._api_factory = lambda: mock_api
    with pytest.raises(KagglePushError, match="Kaggle push failed"):
        gateway._push_sync("user/sicurre-data", tmp_path, "msg")


@pytest.mark.asyncio
async def test_push_version_calls_push_sync(gateway: KaggleGateway, tmp_path: Path) -> None:
    """push_version runs _push_sync in an executor and returns its result."""
    with patch.object(gateway, "_push_sync", return_value=42) as mock_sync:
        result = await gateway.push_version(
            slug="user/sicurre-data",
            export_dir=tmp_path,
            message="auto-publish",
        )

    assert result == 42
    mock_sync.assert_called_once_with("user/sicurre-data", tmp_path, "auto-publish")
