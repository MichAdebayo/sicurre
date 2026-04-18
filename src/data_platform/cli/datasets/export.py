import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# noqa: E402
from data_platform.services.shared.dataset_export import DatasetExportService


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export a frozen Dataset version into ML-ready physical files."
    )
    parser.add_argument(
        "--version-tag",
        type=str,
        required=True,
        help="The dataset version to export (e.g. 1.0.0)",
    )

    args = parser.parse_args()

    try:
        service = DatasetExportService()
        service.export_dataset(version_tag=args.version_tag)
    except ValueError as exc:
        print(f"❌ Export failed: {exc}")
        sys.exit(1)
