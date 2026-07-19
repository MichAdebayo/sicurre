"""Reviewed golden-set publication command tests."""

from __future__ import annotations

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
    monkeypatch.setattr(command, "build_snapshot_store", lambda **_: store)
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
