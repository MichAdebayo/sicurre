import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.shared.stage_two_rewrite_drafts import (  # noqa: E402
    StageTwoRewriteDraftService,
)
from data_platform.services.shared.structured_review_artifact import (  # noqa: E402
    StructuredReviewArtifactService,
)

DEFAULT_INPUT = ROOT_DIR / "tasks/reviews/stage-two-rewrite-jobs.json"
DEFAULT_JSON = ROOT_DIR / "tasks/reviews/stage-two-rewrite-drafts.json"
DEFAULT_MD = ROOT_DIR / "tasks/reviews/stage-two-rewrite-drafts.md"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build no-write rewrite drafts and review states from the stage-two rewrite jobs."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    rewrite_jobs = StructuredReviewArtifactService.read_json(args.input)
    drafts = StageTwoRewriteDraftService.build_drafts(rewrite_jobs)
    StructuredReviewArtifactService.write_json(args.output_json, drafts)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(
        StageTwoRewriteDraftService.render_markdown(drafts),
        encoding="utf-8",
    )

    print(json.dumps(drafts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
