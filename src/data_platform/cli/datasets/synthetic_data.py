from __future__ import annotations

import argparse
import asyncio
import json
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
from data_platform.services.generation_lineage import (  # noqa: E402
    build_synthetic_generation_bundle,
    persist_generation_bundle_payload,
)


async def main() -> None:
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
    parser.add_argument(
        "--persist-lineage",
        action="store_true",
        help="Persist the generated run and samples into data_generation_run/data_generation_sample.",
    )
    parser.add_argument(
        "--promote-usable",
        action="store_true",
        help="After staging lineage, promote usable samples into curated storage.",
    )
    parser.add_argument(
        "--pipeline-version",
        type=str,
        default="synthetic_generation_v1",
        help="Pipeline version to stamp when usable samples are promoted.",
    )
    parser.add_argument(
        "--run-timestamp",
        type=str,
        default=None,
        help="Explicit ISO timestamp for the generation run metadata.",
    )
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Do not write local CSV artifacts; generate in memory only.",
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
    lineage_results: list[tuple[str, dict[str, object]]] = []
    for cls in classes:
        count = args.count if args.count > 0 else DEFAULT_TARGETS.get(cls, 0)
        result = service.generate_result(cls, count, export=not args.skip_export)
        path = result.output_path
        generated_files.append((cls, path))
        if (args.persist_lineage or args.promote_usable) and not result.dataframe.empty:
            bundle = build_synthetic_generation_bundle(
                result.dataframe,
                class_name=cls,
                run_timestamp=args.run_timestamp,
                generated_artifact_uri=(str(path) if path else None),
            )
            lineage_result = await persist_generation_bundle_payload(
                bundle,
                promote_usable=args.promote_usable,
                pipeline_version=args.pipeline_version,
                report_uri=(str(path) if path else None),
            )
            lineage_results.append((cls, lineage_result))

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

    for cls, lineage_result in lineage_results:
        print(f"  🗄️  {cls:<12s} → {json.dumps(lineage_result, ensure_ascii=False)}")

    print("\n  Done! 🎉")


if __name__ == "__main__":
    asyncio.run(main())
