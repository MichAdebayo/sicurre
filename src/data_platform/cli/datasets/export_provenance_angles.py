import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# noqa: E402
from data_platform.services.shared.provenance_angle_export import (
    PROVENANCE_ANGLES,
    ProvenanceAngleExportService,
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export local provenance-angle dataset folders for notebook experiments."
    )
    parser.add_argument(
        "--version-tag",
        type=str,
        help="Frozen dataset version to export. Defaults to the latest frozen version.",
    )

    args = parser.parse_args()
    service = ProvenanceAngleExportService()
    results = service.export_angles(version_tag=args.version_tag)

    print("=" * 60)
    print("SICURRE — Export Provenance Angles")
    print("=" * 60)
    print(f"Export root: {service.output_root}")
    print("Angles:")
    for angle in PROVENANCE_ANGLES:
        suffix = " [analysis-only]" if angle.analysis_only else ""
        print(f"  - {angle.name}{suffix}")
    print("\nGenerated folders:")
    for angle_name, angle_dir in results.items():
        print(f"  - {angle_name}: {angle_dir}")
