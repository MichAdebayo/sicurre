import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
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
        description="Build a no-write Common Crawl promotion review from a structured review artifact."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--approved-subtypes",
        type=str,
        default=",".join(CommonCrawlPromotionReviewService.DEFAULT_APPROVED_SUBTYPES),
        help="Comma-separated subtype list eligible for future promotion review.",
    )
    args = parser.parse_args()

    review_payload = StructuredReviewArtifactService.read_json(args.input)
    approved_subtypes = tuple(
        subtype.strip()
        for subtype in args.approved_subtypes.split(",")
        if subtype.strip()
    )
    plan = CommonCrawlPromotionReviewService.build_plan(
        review_payload,
        approved_subtypes=approved_subtypes,
    )

    if args.output:
        StructuredReviewArtifactService.write_json(args.output, plan)

    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
