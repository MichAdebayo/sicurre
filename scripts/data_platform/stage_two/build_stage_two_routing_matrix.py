import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.shared.stage_two_routing_matrix import (
    StageTwoRoutingMatrixService,
)
from data_platform.services.shared.structured_review_artifact import (
    StructuredReviewArtifactService,
)

DEFAULT_INPUTS = (
    ROOT_DIR / "tasks/reviews/common-crawl-full-review.json",
    ROOT_DIR / "tasks/reviews/certfr-full-review.json",
    ROOT_DIR / "tasks/reviews/database-historical-full-review.json",
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the stage-two routing matrix from structured review artifacts."
    )
    parser.add_argument(
        "--input",
        dest="inputs",
        action="append",
        type=Path,
        default=None,
        help="Structured review JSON path. Can be provided multiple times.",
    )
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    args = parser.parse_args()

    input_paths = args.inputs or list(DEFAULT_INPUTS)
    review_payloads = [
        StructuredReviewArtifactService.read_json(input_path)
        for input_path in input_paths
    ]
    matrix = StageTwoRoutingMatrixService.build_matrix(review_payloads)

    if args.output_json:
        StructuredReviewArtifactService.write_json(args.output_json, matrix)

    markdown = StageTwoRoutingMatrixService.render_markdown(matrix)
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(markdown, encoding="utf-8")

    print(json.dumps(matrix, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
