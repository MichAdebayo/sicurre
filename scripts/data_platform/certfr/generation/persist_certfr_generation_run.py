from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[4]


GENERATED_DEFAULT = ROOT_DIR / "tasks/reviews/certfr-generated-drafts.json"
COMPARISON_DEFAULT = ROOT_DIR / "tasks/reviews/certfr-reference-comparison.json"
MONITOR_DEFAULT = ROOT_DIR / "tasks/reviews/certfr-generation-monitor.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_review_bundle(
    *,
    generated_payload: dict[str, Any],
    comparison_payload: dict[str, Any],
    monitor_payload: dict[str, Any],
    generated_path: Path,
    comparison_path: Path,
    monitor_path: Path,
) -> dict[str, Any]:
    generated_count = int(generated_payload.get("draft_count", 0))
    monitor_count = int(monitor_payload.get("draft_count", 0))
    if generated_count != monitor_count:
        raise ValueError(
            "Generated and monitor artifacts disagree on draft count: "
            f"{generated_count} != {monitor_count}"
        )

    return {
        "mode": "certfr_generation_review_bundle_validation",
        "status": "json_only_review_lane",
        "message": (
            "Persistence is disabled. CERT-FR generation outputs must remain review "
            "artifacts until they are promoted through a traced normalized-message path."
        ),
        "generated_artifact_uri": str(generated_path),
        "comparison_artifact_uri": str(comparison_path),
        "monitor_artifact_uri": str(monitor_path),
        "generated_draft_count": generated_count,
        "comparison_count": len(comparison_payload.get("comparisons", [])),
        "review_summary": generated_payload.get("review_summary", {}),
        "reference_selection_mode": comparison_payload.get("reference_selection_mode"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate CERT-FR review artifacts. This command intentionally does not "
            "write to the database while the lane remains JSON-only."
        )
    )
    parser.add_argument("--generated", type=Path, default=GENERATED_DEFAULT)
    parser.add_argument("--comparison", type=Path, default=COMPARISON_DEFAULT)
    parser.add_argument("--monitor", type=Path, default=MONITOR_DEFAULT)
    args = parser.parse_args()
    generated_payload = read_json(args.generated)
    comparison_payload = read_json(args.comparison)
    monitor_payload = read_json(args.monitor)
    payload = validate_review_bundle(
        generated_payload=generated_payload,
        comparison_payload=comparison_payload,
        monitor_payload=monitor_payload,
        generated_path=args.generated,
        comparison_path=args.comparison,
        monitor_path=args.monitor,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
