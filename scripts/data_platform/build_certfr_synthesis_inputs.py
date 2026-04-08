import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.certfr_synthesis_inputs import (  # noqa: E402
    CertFRSynthesisInputService,
)
from data_platform.services.structured_review_artifact import (  # noqa: E402
    StructuredReviewArtifactService,
)

DEFAULT_INPUT = ROOT_DIR / "tasks/reviews/certfr-signal-summary.json"
DEFAULT_JSON = ROOT_DIR / "tasks/reviews/certfr-synthesis-inputs.json"
DEFAULT_MD = ROOT_DIR / "tasks/reviews/certfr-synthesis-inputs.md"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build CERT-FR phishing synthesis scenarios from the CERT-FR signal summary."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    signal_summary = StructuredReviewArtifactService.read_json(args.input)
    synthesis_inputs = CertFRSynthesisInputService.build_inputs(signal_summary)
    StructuredReviewArtifactService.write_json(args.output_json, synthesis_inputs)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(
        CertFRSynthesisInputService.render_markdown(synthesis_inputs),
        encoding="utf-8",
    )

    print(json.dumps(synthesis_inputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
