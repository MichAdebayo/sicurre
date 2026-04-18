import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.shared.stage_two_rewrite_jobs import (
    StageTwoRewriteJobService,
)
from data_platform.services.shared.structured_review_artifact import (
    StructuredReviewArtifactService,
)

DEFAULT_INPUT = ROOT_DIR / "tasks/reviews/stage-two-adaptation-queue.json"
DEFAULT_JSON = ROOT_DIR / "tasks/reviews/stage-two-rewrite-jobs.json"
DEFAULT_MD = ROOT_DIR / "tasks/reviews/stage-two-rewrite-jobs.md"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build prompt-ready rewrite jobs from the stage-two adaptation queue."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    adaptation_queue = StructuredReviewArtifactService.read_json(args.input)
    jobs = StageTwoRewriteJobService.build_jobs(adaptation_queue)
    StructuredReviewArtifactService.write_json(args.output_json, jobs)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(
        StageTwoRewriteJobService.render_markdown(jobs),
        encoding="utf-8",
    )

    print(json.dumps(jobs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
