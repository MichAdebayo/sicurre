from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class StructuredReviewArtifactService:
    @staticmethod
    def read_json(input_path: Path) -> dict[str, Any]:
        return json.loads(input_path.read_text(encoding="utf-8"))

    @staticmethod
    def build_payload(
        *,
        result: dict[str, Any],
        source_name: str | None,
        source_type: str | None,
        route_outcome_filter: str | None,
        route_subtype_filter: str | None,
    ) -> dict[str, Any]:
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "source_name": source_name,
            "source_type": source_type,
            "route_outcome_filter": route_outcome_filter,
            "route_subtype_filter": route_subtype_filter,
            "result": result,
        }

    @staticmethod
    def write_json(output_path: Path, payload: dict[str, Any]) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
