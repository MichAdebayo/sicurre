from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.adaptation import (  # noqa: E402
    DEFAULT_TARGET_PER_ARCHETYPE,
    FrenchCulturalAdaptationService,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate culturally adapted French phishing emails from an English phishing corpus"
    )
    parser.add_argument(
        "--corpus-path",
        type=Path,
        default=Path("data/raw/csv/en/combined_final_clean.csv"),
        help="Input English phishing corpus CSV",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw/db"),
        help="Output directory for adapted CSV exports",
    )
    parser.add_argument(
        "--target-per-archetype",
        type=int,
        default=DEFAULT_TARGET_PER_ARCHETYPE,
        help="Number of French adapted emails to generate per archetype",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic seed for Faker and template selection",
    )
    args = parser.parse_args()

    service = FrenchCulturalAdaptationService(seed=args.seed)
    source_df = service.load_phishing_corpus(args.corpus_path)
    matched_df = service.attach_archetype_matches(source_df)
    generated_df = service.generate_all_adapted_emails(
        matched_df,
        target_per_archetype=args.target_per_archetype,
    )
    deduplicated_df, removed_duplicates = service.deduplicate_generated(generated_df)
    summary = service.build_summary(
        source_df,
        matched_df,
        deduplicated_df,
        removed_duplicates=removed_duplicates,
    )
    export_result = service.export_adapted_dataframe(deduplicated_df, args.output_dir)

    print(f"Corpus rows kept            : {summary.total_rows:,}")
    print(
        f"Matched to >=1 archetype    : {summary.matched_rows:,} ({summary.matched_ratio:.1%})"
    )
    print(f"Generated rows after dedup  : {summary.deduplicated_rows:,}")
    print(f"Removed duplicates          : {summary.removed_duplicates:,}")
    print(f"Mean text length            : {summary.mean_text_length:.0f}")
    print(f"Min French markers          : {summary.min_french_markers}")
    print(f"Mean French markers         : {summary.mean_french_markers:.1f}")
    print(f"Urgency marker ratio        : {summary.urgency_ratio:.1%}")
    print("Per-archetype source matches:")
    for name, count in sorted(summary.per_archetype_matches.items()):
        print(f"  {name:25s} {count:>6d}")
    print("Per-archetype generated rows:")
    for name, count in sorted(summary.generated_per_archetype.items()):
        print(f"  {name:25s} {count:>6d}")
    print(f"Timestamped export          : {export_result.timestamped_path}")
    print(f"Stable export               : {export_result.stable_path}")


if __name__ == "__main__":
    main()
