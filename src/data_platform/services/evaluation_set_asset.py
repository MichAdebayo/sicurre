"""Validation and canonical serialization for evaluation-only golden sets."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EXPECTED_LABEL_COUNTS = {"phishing": 25, "legitimate": 25, "spam": 10}


class GoldenSetRecord(BaseModel):
    """One human-reviewed, synthetic, evaluation-only email scenario."""

    id: str = Field(pattern=r"^golden-[a-z0-9-]+$")
    subject: str = Field(max_length=500)
    sender: str = Field(max_length=200)
    text: str = Field(max_length=5500)
    expected_label: Literal["phishing", "legitimate", "spam"]
    language: Literal["fr"]
    scenario: str = Field(min_length=1, max_length=200)
    difficulty: Literal["standard", "hard"]
    reviewer_rationale: str = Field(min_length=1, max_length=1000)
    reviewed_by: str = Field(min_length=1, max_length=320)
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class EvaluationAsset:
    """Canonical JSONL and metadata ready for immutable storage."""

    jsonl: bytes
    checksum: str
    item_count: int
    label_counts: dict[str, int]
    language_counts: dict[str, int]


def build_evaluation_asset(records: list[GoldenSetRecord]) -> EvaluationAsset:
    """Validate composition and serialize a reviewed provisional golden set."""
    identifiers = [record.id for record in records]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Golden-set record IDs must be unique")
    label_counts = {
        label: sum(record.expected_label == label for record in records)
        for label in EXPECTED_LABEL_COUNTS
    }
    if label_counts != EXPECTED_LABEL_COUNTS:
        raise ValueError(
            f"Golden-set label composition must be {EXPECTED_LABEL_COUNTS}, got {label_counts}"
        )
    language_counts = {"fr": len(records)}
    lines = [
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        for record in sorted(records, key=lambda item: item.id)
    ]
    payload = ("\n".join(lines) + "\n").encode()
    return EvaluationAsset(
        jsonl=payload,
        checksum=hashlib.sha256(payload).hexdigest(),
        item_count=len(records),
        label_counts=label_counts,
        language_counts=language_counts,
    )


def load_evaluation_records(payload: bytes) -> list[GoldenSetRecord]:
    """Parse reviewed JSONL with line-specific validation errors."""
    records: list[GoldenSetRecord] = []
    for line_number, line in enumerate(payload.decode().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(GoldenSetRecord.model_validate_json(line))
        except Exception as exc:
            raise ValueError(f"Invalid golden-set record at line {line_number}") from exc
    return records
