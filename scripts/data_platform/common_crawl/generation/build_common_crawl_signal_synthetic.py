from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.common_crawl_signal_synthetic import (
    CommonCrawlSignalSyntheticService,
)
from data_platform.services.generation_staging import GenerationStagingService
from data_platform.services.structured_review_artifact import (
    StructuredReviewArtifactService,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build Common Crawl real-signal synthetic phishing drafts from the reviewed "
            "export and stage them as a no-write generation bundle."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--bundle-json", type=Path, required=True)
    parser.add_argument("--bundle-md", type=Path, required=True)
    parser.add_argument("--variants-per-seed", type=int, default=2)
    args = parser.parse_args()

    export_payload = StructuredReviewArtifactService.read_json(args.input)
    drafts_payload = CommonCrawlSignalSyntheticService.build_drafts(
        export_payload,
        variants_per_seed=args.variants_per_seed,
    )
    StructuredReviewArtifactService.write_json(args.output_json, drafts_payload)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(
        CommonCrawlSignalSyntheticService.render_markdown(drafts_payload),
        encoding="utf-8",
    )

    bundle = GenerationStagingService.build_bundle(
        generator_name="common_crawl_signal_synthetic",
        source_name="common-crawl-phishing-signal",
        parent_source="common-crawl-bigdata",
        reference_selection_mode="reviewed_export_phishing_seed",
        input_artifact_uri=str(args.input),
        generated_artifact_uri=str(args.output_json),
        samples=CommonCrawlSignalSyntheticService.build_generation_samples(
            drafts_payload
        ),
    )
    StructuredReviewArtifactService.write_json(args.bundle_json, bundle)
    args.bundle_md.parent.mkdir(parents=True, exist_ok=True)
    args.bundle_md.write_text(
        GenerationStagingService.render_markdown(bundle),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "drafts": drafts_payload,
                "bundle": bundle,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
