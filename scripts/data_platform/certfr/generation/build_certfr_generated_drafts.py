import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.certfr_generated_drafts import (  # noqa: E402
    CertFRGeneratedDraftService,
)
from data_platform.services.structured_review_artifact import (  # noqa: E402
    StructuredReviewArtifactService,
)

DEFAULT_INPUT = ROOT_DIR / "tasks/reviews/certfr-synthesis-inputs.json"
DEFAULT_JSON = ROOT_DIR / "tasks/reviews/certfr-generated-drafts.json"
DEFAULT_MD = ROOT_DIR / "tasks/reviews/certfr-generated-drafts.md"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build deterministic phishing draft outputs from CERT-FR synthesis scenarios."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    synthesis_payload = StructuredReviewArtifactService.read_json(args.input)
    drafts = CertFRGeneratedDraftService.build_drafts(synthesis_payload)
    StructuredReviewArtifactService.write_json(args.output_json, drafts)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(
        CertFRGeneratedDraftService.render_markdown(drafts),
        encoding="utf-8",
    )

    print(json.dumps(drafts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
