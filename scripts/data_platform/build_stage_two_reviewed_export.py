import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.stage_two_reviewed_export import (  # noqa: E402
    StageTwoReviewedExportService,
)
from data_platform.services.structured_review_artifact import (  # noqa: E402
    StructuredReviewArtifactService,
)

DEFAULT_INPUT = ROOT_DIR / "tasks/reviews/stage-two-rewrite-drafts.json"
DEFAULT_JSON = ROOT_DIR / "tasks/reviews/stage-two-reviewed-export.json"
DEFAULT_MD = ROOT_DIR / "tasks/reviews/stage-two-reviewed-export.md"
DEFAULT_CSV = ROOT_DIR / "tasks/reviews/stage-two-reviewed-export.csv"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build no-write reviewed export candidates from usable stage-two rewrite drafts."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument(
        "--eligible-review-states",
        type=str,
        default="usable",
        help="Comma-separated review states eligible for export.",
    )
    args = parser.parse_args()

    draft_payload = StructuredReviewArtifactService.read_json(args.input)
    eligible_review_states = tuple(
        state.strip()
        for state in args.eligible_review_states.split(",")
        if state.strip()
    )
    service = StageTwoReviewedExportService()
    export_payload = service.build_export(
        draft_payload,
        eligible_review_states=eligible_review_states,
    )

    StructuredReviewArtifactService.write_json(args.output_json, export_payload)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(
        StageTwoReviewedExportService.render_markdown(export_payload),
        encoding="utf-8",
    )
    StageTwoReviewedExportService.write_csv(export_payload, args.output_csv)

    print(json.dumps(export_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
