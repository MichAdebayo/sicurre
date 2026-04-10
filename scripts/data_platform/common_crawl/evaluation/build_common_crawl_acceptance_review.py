import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.common_crawl_promotion_review import (
    CommonCrawlPromotionReviewService,
)
from data_platform.services.structured_review_artifact import (
    StructuredReviewArtifactService,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build a no-write Common Crawl acceptance review from the reviewed export "
            "artifact using conservative parity with direct-write sources."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    export_payload = StructuredReviewArtifactService.read_json(args.input)
    review = CommonCrawlPromotionReviewService.build_acceptance_review(export_payload)
    StructuredReviewArtifactService.write_json(args.output_json, review)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(
        CommonCrawlPromotionReviewService.render_acceptance_markdown(review),
        encoding="utf-8",
    )
    print(json.dumps(review, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
