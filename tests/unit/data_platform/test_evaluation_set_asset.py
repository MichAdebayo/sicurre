"""Evaluation-only asset validation tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from data_platform.services.evaluation_set_asset import (
    GoldenSetRecord,
    build_evaluation_asset,
    load_evaluation_records,
)


def reviewed_records() -> list[GoldenSetRecord]:
    """Build the approved 25/25/10 provisional composition."""
    records: list[GoldenSetRecord] = []
    for label, count in (("phishing", 25), ("legitimate", 25), ("spam", 10)):
        for index in range(count):
            records.append(
                GoldenSetRecord(
                    id=f"golden-{label}-{index:02d}",
                    subject=f"Scenario {label} {index}",
                    sender=f"sender-{index}@example.test",
                    text=f"Synthetic {label} message {index} with hxxps://example[.]test",
                    expected_label=label,
                    language="fr",
                    scenario=f"{label} scenario",
                    difficulty="hard" if label != "spam" else "standard",
                    reviewer_rationale="Reviewed synthetic boundary example.",
                    reviewed_by="owner@sicurre.com",
                    reviewed_at=datetime(2026, 7, 19, 10, tzinfo=UTC),
                )
            )
    return records


def test_reviewed_evaluation_asset_is_canonical_and_round_trips() -> None:
    """Approved records serialize deterministically and retain all 60 rows."""
    records = reviewed_records()
    first = build_evaluation_asset(records)
    second = build_evaluation_asset(list(reversed(records)))
    assert first.jsonl == second.jsonl
    assert first.checksum == second.checksum
    assert first.label_counts == {"phishing": 25, "legitimate": 25, "spam": 10}
    assert first.language_counts == {"fr": 60}
    assert len(load_evaluation_records(first.jsonl)) == 60


def test_evaluation_asset_rejects_duplicate_ids_and_wrong_composition() -> None:
    """An accidental duplicate or class-count drift prevents publication."""
    records = reviewed_records()
    records[-1] = records[0]
    with pytest.raises(ValueError, match="unique"):
        build_evaluation_asset(records)
    with pytest.raises(ValueError, match="composition"):
        build_evaluation_asset(reviewed_records()[:-1])


def test_evaluation_loader_reports_invalid_line() -> None:
    """Malformed review assets identify the offending JSONL line."""
    valid_line = reviewed_records()[0].model_dump_json().encode()
    with pytest.raises(ValueError, match="line 2"):
        load_evaluation_records(valid_line + b"\nnot-json\n")


def test_evaluation_loader_rejects_non_french_records() -> None:
    """The evaluation set follows Sicurre's French-only model contract."""
    english = reviewed_records()[0].model_dump()
    english["language"] = "en"
    with pytest.raises(ValueError, match="line 1"):
        load_evaluation_records(json.dumps(english, default=str).encode())
