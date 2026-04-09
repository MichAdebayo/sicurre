import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.certfr_signal_summary import CertFRSignalSummaryService
from data_platform.services.structured_review_artifact import (
    StructuredReviewArtifactService,
)

DEFAULT_INPUT = ROOT_DIR / "tasks/reviews/stage-two-signal-bank.json"
DEFAULT_JSON = ROOT_DIR / "tasks/reviews/certfr-signal-summary.json"
DEFAULT_MD = ROOT_DIR / "tasks/reviews/certfr-signal-summary.md"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a condensed CERT-FR threat-intel signal summary from the signal bank."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    signal_bank = StructuredReviewArtifactService.read_json(args.input)
    summary = CertFRSignalSummaryService.build_summary(signal_bank)
    StructuredReviewArtifactService.write_json(args.output_json, summary)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(
        CertFRSignalSummaryService.render_markdown(summary),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
