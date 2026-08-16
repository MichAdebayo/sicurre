"""Reviewed golden-set publication command tests."""

from __future__ import annotations

import sys
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from data_platform.cli.datasets import publish_evaluation_set as command
from data_platform.services.evaluation_set_asset import GoldenSetRecord
from data_platform.services.shared.snapshot_storage import SnapshotWriteResult


def write_reviewed_asset(path: Path) -> None:
    """Write the required 25/25/10 reviewed JSONL composition."""
    lines: list[str] = []
    for label, count in (("phishing", 25), ("legitimate", 25), ("spam", 10)):
        for index in range(count):
            lines.append(
                GoldenSetRecord(
                    id=f"golden-{label}-{index}",
                    subject="Synthetic subject",
                    sender="sender@example.test",
                    text="Defanged synthetic message",
                    expected_label=label,
                    language="fr",
                    scenario=f"{label} scenario",
                    difficulty="standard",
                    reviewer_rationale="Human-reviewed expected behavior.",
                    reviewed_by="owner@sicurre.com",
                    reviewed_at=datetime(2026, 7, 19, tzinfo=UTC),
                ).model_dump_json()
            )
    path.write_text("\n".join(lines) + "\n")


@pytest.mark.asyncio
async def test_publish_evaluation_set_stores_and_registers_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command writes canonical JSONL then persists matching metadata."""
    input_path = tmp_path / "golden.jsonl"
    write_reviewed_asset(input_path)
    class Store:
        def __init__(self) -> None:
            self.write_snapshot = AsyncMock(
                return_value=SnapshotWriteResult(
                    storage_uri="r2://evaluation/evaluation_sets/golden-v1/golden.jsonl",
                    content_hash="unused",
                    size_bytes=1,
                )
            )

        def build_object_key(self, **_: object) -> str:
            return "evaluation_sets/golden-v1/golden.jsonl"

    store = Store()

    class SessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_: object) -> None:
            return None

    register = AsyncMock()
    monkeypatch.setattr(command, "build_evaluation_set_store", lambda **_: store)
    monkeypatch.setattr(command, "AsyncSessionFactory", lambda: SessionContext())
    monkeypatch.setattr(command, "register_evaluation_set", register)
    args = Namespace(
        input=input_path,
        version_tag="golden-v1",
        reviewed_by="owner@sicurre.com",
        reviewed_at="2026-07-19T10:00:00Z",
        backend="r2",
    )

    registration = await command.publish(args)

    assert registration.status == "approved"
    assert registration.item_count == 60
    assert registration.object_uri.startswith("r2://evaluation/")
    store.write_snapshot.assert_awaited_once()
    register.assert_awaited_once()


def test_publish_cli_parses_and_prints_registration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The publication entrypoint preserves explicit reviewer arguments."""
    input_path = tmp_path / "golden.jsonl"
    input_path.write_text("{}\n")
    registration = command.EvaluationSetRegistration.model_validate(
        {
            "name": "golden",
            "version_tag": "golden-v1",
            "schema_version": "1",
            "provenance": "synthetic_provisional",
            "status": "approved",
            "object_uri": "r2://evaluation/golden.jsonl",
            "content_checksum": "a" * 64,
            "item_count": 60,
            "label_counts": {"phishing": 25, "legitimate": 25, "spam": 10},
            "language_counts": {"fr": 60},
            "reviewed_by": "repository-owner",
            "reviewed_at": "2026-07-19T17:29:21Z",
        }
    )
    publish = AsyncMock(return_value=registration)
    monkeypatch.setattr(command, "publish", publish)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "publish",
            "--input",
            str(input_path),
            "--version-tag",
            "golden-v1",
            "--reviewed-by",
            "repository-owner",
            "--reviewed-at",
            "2026-07-19T17:29:21Z",
            "--backend",
            "r2",
        ],
    )
    command.main()
    assert '"version_tag": "golden-v1"' in capsys.readouterr().out
    publish.assert_awaited_once()


def test_evaluation_store_addresses_the_dedicated_bucket(monkeypatch, tmp_path) -> None:
    """The published URI must name the bucket Sicurre-ML actually reads.

    The shared snapshot store resolves every R2 backend to the raw ingestion
    bucket, so publishing through it wrote the golden set to `sicurre-raw`
    while the ML repository read from `sicurre-golden-evaluation-dataset`. The
    publish reported success and registered an object_uri nothing could fetch.
    """
    from core.config import get_settings
    from data_platform.services.shared.snapshot_storage import build_evaluation_set_store

    get_settings.cache_clear()
    monkeypatch.setenv("SICURRE_EVALUATION_SET_R2_BUCKET_NAME", "sicurre-golden-evaluation-dataset")
    monkeypatch.setenv("SICURRE_EVALUATION_SET_R2_ENDPOINT_URL", "https://r2.test")
    monkeypatch.setenv("SICURRE_EVALUATION_SET_R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("SICURRE_EVALUATION_SET_R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("SICURRE_RAW_SNAPSHOT_R2_BUCKET_NAME", "sicurre-raw")

    store = build_evaluation_set_store(
        local_root_dir=tmp_path, repo_root=tmp_path, backend="r2"
    )

    assert store.bucket_name == "sicurre-golden-evaluation-dataset"
    assert store.bucket_name != "sicurre-raw"
    # The raw prefix must not be applied: the contract path is
    # evaluation_sets/<version>/golden.jsonl at the bucket root.
    assert store.root_prefix == ""
    get_settings.cache_clear()


def test_evaluation_publish_refuses_to_fall_back_to_the_raw_bucket(
    monkeypatch, tmp_path
) -> None:
    """A missing evaluation bucket must fail loudly, not silently reuse raw."""
    from core.config import get_settings
    from data_platform.services.shared.snapshot_storage import build_evaluation_set_store

    get_settings.cache_clear()
    for name in (
        "SICURRE_EVALUATION_SET_R2_BUCKET_NAME",
        "SICURRE_EVALUATION_SET_R2_ENDPOINT_URL",
        "SICURRE_EVALUATION_SET_R2_ACCESS_KEY_ID",
        "SICURRE_EVALUATION_SET_R2_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SICURRE_RAW_SNAPSHOT_R2_BUCKET_NAME", "sicurre-raw")

    with pytest.raises(RuntimeError, match="must not fall back to the raw snapshot bucket"):
        build_evaluation_set_store(
            local_root_dir=tmp_path, repo_root=tmp_path, backend="r2"
        )
    get_settings.cache_clear()
