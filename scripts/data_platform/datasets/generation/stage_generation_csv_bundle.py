from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.cleaning.normalization import text_sha256
from data_platform.services.generation_staging import GenerationStagingService
from data_platform.services.structured_review_artifact import (
    StructuredReviewArtifactService,
)


LABEL_MAP = {
    "0": "phishing",
    "1": "spam",
    "2": "legitimate",
    "phishing": "phishing",
    "spam": "spam",
    "legitimate": "legitimate",
}


def _coerce_label(value: object) -> str:
    return LABEL_MAP.get(str(value).strip().lower(), "unknown")


def _build_samples(
    dataframe: pd.DataFrame, source_name: str
) -> list[dict[str, object]]:
    samples: list[dict[str, object]] = []
    for index, row in dataframe.reset_index(drop=True).iterrows():
        text = str(row.get("text") or "").strip()
        samples.append(
            {
                "draft_id": f"{source_name}:{index}",
                "scenario_id": str(
                    row.get("archetype") or row.get("source") or source_name
                ),
                "variant_index": 0,
                "source_name": source_name,
                "parent_source": str(row.get("source") or source_name),
                "target_label": _coerce_label(row.get("label")),
                "primary_theme": str(row.get("archetype") or ""),
                "review_state": "usable",
                "review_notes": [],
                "text_sha256": text_sha256(text) if text else None,
                "nearest_reference_raw_record_id": None,
                "nearest_similarity": None,
            }
        )
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage an adapted or synthetic CSV as a no-write generation bundle."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--generator-name", type=str, required=True)
    parser.add_argument("--source-name", type=str, required=True)
    parser.add_argument("--parent-source", type=str, default=None)
    parser.add_argument("--reference-selection-mode", type=str, default=None)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    dataframe = pd.read_csv(args.input)
    samples = _build_samples(dataframe, args.source_name)
    bundle = GenerationStagingService.build_bundle(
        generator_name=args.generator_name,
        source_name=args.source_name,
        parent_source=args.parent_source,
        reference_selection_mode=args.reference_selection_mode,
        input_artifact_uri=str(args.input),
        generated_artifact_uri=str(args.input),
        samples=samples,
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
