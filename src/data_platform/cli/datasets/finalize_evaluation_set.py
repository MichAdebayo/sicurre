"""Stamp an approved review draft and write its canonical immutable JSONL."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from data_platform.services.evaluation_set_asset import GoldenSetRecord, build_evaluation_asset


def parse_args() -> argparse.Namespace:
    """Parse the explicit reviewer and artifact destinations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reviewed-by", required=True)
    parser.add_argument("--reviewed-at", type=datetime.fromisoformat, required=True)
    return parser.parse_args()


def finalize(
    input_path: Path,
    output_path: Path,
    *,
    reviewed_by: str,
    reviewed_at: datetime,
) -> str:
    """Convert an approved pending draft into canonical reviewed JSONL."""
    records: list[GoldenSetRecord] = []
    for line_number, line in enumerate(input_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        payload: dict[str, Any] = json.loads(line)
        if payload.pop("review_status", None) != "pending":
            raise ValueError(f"Draft record at line {line_number} is not pending review")
        payload.update(
            reviewer_rationale=f"Scénario relu et approuvé : {payload['scenario']}.",
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
        )
        records.append(GoldenSetRecord.model_validate(payload))
    asset = build_evaluation_asset(records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(asset.jsonl)
    return asset.checksum


def main() -> None:
    """Finalize one explicitly approved review draft."""
    args = parse_args()
    checksum = finalize(
        args.input,
        args.output,
        reviewed_by=args.reviewed_by,
        reviewed_at=args.reviewed_at,
    )
    print(checksum)


if __name__ == "__main__":
    main()
