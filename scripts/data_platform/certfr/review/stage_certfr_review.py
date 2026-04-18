import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.certfr.review_staging import CertFRReviewStagingService
from data_platform.services.shared.structured_review_artifact import (
    StructuredReviewArtifactService,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a no-write CERT-FR staging review from a structured review artifact."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    review_payload = StructuredReviewArtifactService.read_json(args.input)
    stage_payload = CertFRReviewStagingService.build_stage_payload(review_payload)

    if args.output:
        StructuredReviewArtifactService.write_json(args.output, stage_payload)

    print(json.dumps(stage_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
