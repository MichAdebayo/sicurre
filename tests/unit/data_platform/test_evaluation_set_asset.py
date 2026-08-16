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


def _records(*, phishing: int, legitimate: int, spam: int) -> list[GoldenSetRecord]:
    """Build a composition with explicit per-class counts."""
    records: list[GoldenSetRecord] = []
    for label, count in (("phishing", phishing), ("legitimate", legitimate), ("spam", spam)):
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
                    difficulty="standard",
                    reviewer_rationale=f"Reviewed {label} {index}",
                    reviewed_by="MichAdebayo",
                    reviewed_at=datetime(2026, 7, 19, 10, tzinfo=UTC),
                )
            )
    return records


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
    with pytest.raises(ValueError, match="at least"):
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


def test_growth_is_allowed_when_phishing_and_legitimate_stay_balanced() -> None:
    """v2 adds an administrative-impersonation block on top of v1's BEC records.

    A fixed 25/25/10 composition blocked the set from ever growing, which is
    how it came to cover business email compromise thoroughly while carrying no
    administrative-impersonation records at all.
    """
    records = _records(phishing=37, legitimate=37, spam=10)

    asset = build_evaluation_asset(records)

    assert asset.item_count == 84
    assert asset.label_counts == {"phishing": 37, "legitimate": 37, "spam": 10}


def test_unbalanced_growth_is_rejected() -> None:
    """Adding phishing alone would move aggregate metrics by composition."""
    records = _records(phishing=37, legitimate=25, spam=10)

    with pytest.raises(ValueError, match="must be equal"):
        build_evaluation_asset(records)


def test_shrinking_below_the_version_one_floor_is_rejected() -> None:
    """Records may be added or corrected, but coverage must not regress."""
    records = _records(phishing=20, legitimate=20, spam=10)

    with pytest.raises(ValueError, match="at least"):
        build_evaluation_asset(records)
