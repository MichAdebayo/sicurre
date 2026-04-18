import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.shared.stage_two_action_artifacts import (  # noqa: E402
    StageTwoActionArtifactsService,
)
from data_platform.services.shared.structured_review_artifact import (  # noqa: E402
    StructuredReviewArtifactService,
)

DEFAULT_MATRIX = ROOT_DIR / "tasks/reviews/stage-two-routing-matrix.json"
DEFAULT_INPUTS = (
    ROOT_DIR / "tasks/reviews/common-crawl-full-review.json",
    ROOT_DIR / "tasks/reviews/certfr-full-review.json",
    ROOT_DIR / "tasks/reviews/database-historical-full-review.json",
)
DEFAULT_ADAPTATION = ROOT_DIR / "tasks/reviews/stage-two-adaptation-queue.json"
DEFAULT_SIGNAL = ROOT_DIR / "tasks/reviews/stage-two-signal-bank.json"
DEFAULT_ARCHIVE = ROOT_DIR / "tasks/reviews/stage-two-archive-manifest.json"
DEFAULT_SUMMARY = ROOT_DIR / "tasks/reviews/stage-two-downstream-artifacts.md"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build downstream stage-two artifacts from the routing matrix and review artifacts."
    )
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument(
        "--input",
        dest="inputs",
        action="append",
        type=Path,
        default=None,
        help="Structured review JSON path. Can be provided multiple times.",
    )
    parser.add_argument("--adaptation-output", type=Path, default=DEFAULT_ADAPTATION)
    parser.add_argument("--signal-output", type=Path, default=DEFAULT_SIGNAL)
    parser.add_argument("--archive-output", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    matrix_payload = StructuredReviewArtifactService.read_json(args.matrix)
    input_paths = args.inputs or list(DEFAULT_INPUTS)
    review_payloads = [
        StructuredReviewArtifactService.read_json(input_path)
        for input_path in input_paths
    ]
    artifacts = StageTwoActionArtifactsService.build_artifacts(
        matrix_payload=matrix_payload,
        review_payloads=review_payloads,
    )

    StructuredReviewArtifactService.write_json(
        args.adaptation_output,
        artifacts["adaptation_queue"],
    )
    StructuredReviewArtifactService.write_json(
        args.signal_output,
        artifacts["signal_bank"],
    )
    StructuredReviewArtifactService.write_json(
        args.archive_output,
        artifacts["archive_manifest"],
    )
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(
        StageTwoActionArtifactsService.render_markdown(artifacts),
        encoding="utf-8",
    )

    print(json.dumps(artifacts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
