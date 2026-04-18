from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.shared.generation_staging import GenerationStagingService
from data_platform.services.shared.structured_review_artifact import (
    StructuredReviewArtifactService,
)


def _build_samples(payload: dict[str, object]) -> list[dict[str, object]]:
    drafts = list(payload.get("drafts") or [])
    samples: list[dict[str, object]] = []
    for draft in drafts:
        samples.append(
            {
                "draft_id": str(draft.get("draft_id") or ""),
                "scenario_id": str(draft.get("scenario_id") or ""),
                "variant_index": int(draft.get("variant_index") or 0),
                "source_name": str(draft.get("source_name") or "cert-fr-cti"),
                "parent_source": "cert-fr-cti",
                "target_label": str(draft.get("target_label") or "phishing"),
                "primary_theme": draft.get("primary_theme"),
                "review_state": str(draft.get("review_state") or "usable"),
                "review_notes": list(draft.get("review_notes") or []),
                "text_sha256": draft.get("text_sha256"),
                "nearest_reference_raw_record_id": (
                    str(draft.get("seed_record_ids")[0])
                    if draft.get("seed_record_ids")
                    else None
                ),
                "nearest_similarity": None,
            }
        )
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage CERT-FR generated phishing drafts as a no-write generation bundle."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    bundle = GenerationStagingService.build_bundle(
        generator_name="certfr_signal_synthetic",
        source_name="certfr-phishing-signal",
        parent_source="cert-fr-cti",
        reference_selection_mode="certfr_signal_scenario_seed",
        input_artifact_uri=str(args.input),
        generated_artifact_uri=str(args.input),
        samples=_build_samples(payload),
    )
    StructuredReviewArtifactService.write_json(args.output_json, bundle)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(
        GenerationStagingService.render_markdown(bundle),
        encoding="utf-8",
    )
    print(json.dumps(bundle, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
