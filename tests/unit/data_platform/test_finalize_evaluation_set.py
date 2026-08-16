"""Golden-set human-review finalization tests."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from data_platform.cli.datasets import finalize_evaluation_set as command
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


def test_finalize_ignores_blank_lines(tmp_path: Path) -> None:
    """Review formatting whitespace does not alter the canonical asset."""
    draft = tmp_path / "draft.jsonl"
    _draft(draft)
    draft.write_text("\n" + draft.read_text() + "\n")
    checksum = finalize(
        draft,
        tmp_path / "golden.jsonl",
        reviewed_by="repository-owner",
        reviewed_at=datetime(2026, 7, 19, tzinfo=UTC),
    )
    assert len(checksum) == 64


def test_finalize_cli_parses_and_prints_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The operational entrypoint forwards explicit review evidence."""
    draft = tmp_path / "draft.jsonl"
    output = tmp_path / "golden.jsonl"
    _draft(draft)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "finalize",
            "--input",
            str(draft),
            "--output",
            str(output),
            "--reviewed-by",
            "repository-owner",
            "--reviewed-at",
            "2026-07-19T17:29:21+00:00",
        ],
    )
    command.main()
    assert len(capsys.readouterr().out.strip()) == 64
    assert output.exists()


def _reviewed_draft(path: Path, *, drop_field: str | None = None) -> None:
    """Write a draft of already-reviewed records carried forward from v1."""
    rows = []
    for label, count in (("phishing", 25), ("legitimate", 25), ("spam", 10)):
        for index in range(count):
            row = {
                "id": f"golden-{label}-{index}",
                "subject": f"Objet {index}",
                "sender": f"sender-{index}@example.test",
                "text": f"Message français synthétique {label} numéro {index}.",
                "expected_label": label,
                "language": "fr",
                "scenario": "Scénario synthétique revu",
                "difficulty": "hard",
                "reviewer_rationale": "Relu lors de la version une.",
                "reviewed_by": "MichAdebayo",
                "reviewed_at": "2026-07-19T17:29:21Z",
                "review_status": "reviewed",
            }
            if drop_field:
                row.pop(drop_field)
            rows.append(row)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_carried_forward_records_keep_their_original_review_provenance(
    tmp_path: Path,
) -> None:
    """Restamping would make an eight-week-old review look like it happened today."""
    draft = tmp_path / "draft.jsonl"
    output = tmp_path / "golden.jsonl"
    _reviewed_draft(draft)

    finalize(
        draft,
        output,
        reviewed_by="SomeoneElse",
        reviewed_at=datetime(2026, 8, 16, 9, 20, tzinfo=UTC),
    )

    records = load_evaluation_records(output.read_bytes())
    assert {record.reviewed_by for record in records} == {"MichAdebayo"}
    assert {record.reviewed_at.date().isoformat() for record in records} == {"2026-07-19"}


@pytest.mark.parametrize(
    "missing_field", ["reviewer_rationale", "reviewed_by", "reviewed_at"]
)
def test_reviewed_records_must_carry_complete_provenance(
    tmp_path: Path, missing_field: str
) -> None:
    """A record claiming prior review must prove it."""
    draft = tmp_path / "draft.jsonl"
    _reviewed_draft(draft, drop_field=missing_field)

    with pytest.raises(ValueError, match=missing_field):
        finalize(
            draft,
            tmp_path / "golden.jsonl",
            reviewed_by="MichAdebayo",
            reviewed_at=datetime(2026, 8, 16, 9, 20, tzinfo=UTC),
        )


def test_unknown_review_status_is_rejected(tmp_path: Path) -> None:
    """Only explicit pending or reviewed states may enter a published version."""
    draft = tmp_path / "draft.jsonl"
    draft.write_text(
        json.dumps({"id": "golden-x", "review_status": "draft"}) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="not pending review"):
        finalize(
            draft,
            tmp_path / "golden.jsonl",
            reviewed_by="MichAdebayo",
            reviewed_at=datetime(2026, 8, 16, 9, 20, tzinfo=UTC),
        )
