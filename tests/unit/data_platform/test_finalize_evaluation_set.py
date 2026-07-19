"""Golden-set human-review finalization tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from data_platform.cli.datasets.finalize_evaluation_set import finalize
from data_platform.services.evaluation_set_asset import load_evaluation_records


def _draft(path: Path, *, status: str = "pending") -> None:
    rows = []
    for label, count in (("phishing", 25), ("legitimate", 25), ("spam", 10)):
        for index in range(count):
            rows.append(
                {
                    "id": f"golden-{label}-{index}",
                    "subject": f"Objet {index}",
                    "sender": f"sender-{index}@example.test",
                    "text": f"Message français synthétique {label} numéro {index}.",
                    "expected_label": label,
                    "language": "fr",
                    "scenario": "Scénario synthétique revu",
                    "difficulty": "hard",
                    "review_status": status,
                }
            )
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")


def test_finalize_stamps_review_and_writes_canonical_asset(tmp_path: Path) -> None:
    """An approved draft becomes a valid immutable evaluation asset."""
    draft = tmp_path / "draft.jsonl"
    output = tmp_path / "golden.jsonl"
    _draft(draft)
    checksum = finalize(
        draft,
        output,
        reviewed_by="repository-owner",
        reviewed_at=datetime(2026, 7, 19, 17, 29, tzinfo=UTC),
    )
    records = load_evaluation_records(output.read_bytes())
    assert len(checksum) == 64
    assert len(records) == 60
    assert {record.reviewed_by for record in records} == {"repository-owner"}


def test_finalize_rejects_non_pending_input(tmp_path: Path) -> None:
    """Finalization cannot silently restamp a previously processed draft."""
    draft = tmp_path / "draft.jsonl"
    _draft(draft, status="approved")
    with pytest.raises(ValueError, match="not pending"):
        finalize(
            draft,
            tmp_path / "golden.jsonl",
            reviewed_by="repository-owner",
            reviewed_at=datetime(2026, 7, 19, tzinfo=UTC),
        )
