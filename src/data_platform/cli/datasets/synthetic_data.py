from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.synthetic_generation import (  # noqa: E402
    DEFAULT_TARGETS,
    TODAY,
    SyntheticGenerationService,
)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate synthetic French emails from archetypes"
    )
    parser.add_argument(
        "--class",
        "-c",
        dest="cls",
        choices=["phishing", "spam", "legitimate", "all"],
        default="all",
        help="Which class to generate (default: all)",
    )
    parser.add_argument(
        "--count",
        "-n",
        type=int,
        default=0,
        help="Number of emails to generate (0 = use defaults)",
    )
    parser.add_argument(
        "--seed",
        "-s",
        type=int,
        default=42,
        help="Random seed for reproducibility",
    )
    args = parser.parse_args()

    service = SyntheticGenerationService(seed=args.seed)
    classes = ["phishing", "spam", "legitimate"] if args.cls == "all" else [args.cls]
    print("=" * 60)
    print("  SICURRE — Synthetic Email Generator")
    print(f"  Date: {TODAY}")
    print(f"  Seed: {args.seed}")
    print("=" * 60)

    generated_files: list[tuple[str, Path | None]] = []
    for cls in classes:
        count = args.count if args.count > 0 else DEFAULT_TARGETS.get(cls, 0)
        path = service.generate_and_save(cls, count)
        generated_files.append((cls, path))

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    for cls, path in generated_files:
        if path and path.exists():
            dataframe = __import__("pandas").read_csv(path)
            print(f"  ✅ {cls:<12s} → {path.name} ({len(dataframe)} rows)")
            service.print_archetype_report(path)
        else:
            print(f"  ⏭️  {cls:<12s} → skipped")

    print("\n  Done! 🎉")
