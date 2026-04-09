"""
Merge all processed CSVs into stratified train/val/test splits.

Reads all CSVs from data/processed/ (excluding phishing_url/ metadata),
merges them into a single DataFrame, then performs stratified splitting
by class AND source type (real vs synthetic) to ensure balanced representation.

Split ratio: 80% train / 10% val / 10% test

Output: data/final/{train,val,test}/sicurre_{split}.csv

Usage:
    python scripts/data_platform/datasets/preparation/merge_splits.py
    python scripts/data_platform/datasets/preparation/merge_splits.py --downsample-to 10000  # cap per class
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import date
from pathlib import Path

import pandas as pd

# ── Constants ──────────────────────────────────────────────────
BASE = Path(__file__).resolve().parents[4]
PROC = BASE / "data" / "processed"
FINAL = BASE / "data" / "final"
TODAY = date.today().strftime("%Y%m%d")

# Output columns from the shared processing pipeline
OUTPUT_COLS = ["text", "label", "source", "language", "archetype", "text_len"]

# Files to EXCLUDE from text-based merge (URL metadata, not email body)
EXCLUDE_DIRS = {"phishing_url"}

# Class label mapping
LABEL_NAMES = {0: "phishing", 1: "spam", 2: "legitimate"}

# Split ratios
TRAIN_RATIO = 0.80
VAL_RATIO = 0.10
TEST_RATIO = 0.10

RANDOM_STATE = 42


def collect_csvs() -> pd.DataFrame:
    """Collect all processed CSVs into a single DataFrame."""
    dfs: list[pd.DataFrame] = []

    for csv_path in sorted(PROC.rglob("*.csv")):
        # Skip excluded directories
        if any(part in EXCLUDE_DIRS for part in csv_path.parts):
            print(f"  ⏭️  Skipping (URL metadata): {csv_path.relative_to(PROC)}")
            continue

        df = pd.read_csv(csv_path)

        # Ensure required columns exist
        for col in OUTPUT_COLS:
            if col not in df.columns:
                df[col] = ""

        # Add is_synthetic flag for stratification
        is_synth = (
            "synth" in csv_path.stem.lower() or "synthetic" in csv_path.stem.lower()
        )
        df["is_synthetic"] = is_synth

        print(
            f"  📄 {csv_path.relative_to(PROC)}: {len(df)} rows "
            f"({'synthetic' if is_synth else 'real'})"
        )

        dfs.append(df[OUTPUT_COLS + ["is_synthetic"]])

    if not dfs:
        raise RuntimeError("No CSV files found in data/processed/")

    merged = pd.concat(dfs, ignore_index=True)
    return merged


def global_dedup(df: pd.DataFrame) -> pd.DataFrame:
    """Remove duplicates across all sources using SHA-256 of first 300 chars."""
    before = len(df)
    df = df.copy()
    df["_hash"] = (
        df["text"]
        .astype(str)
        .str[:300]
        .apply(lambda t: hashlib.sha256(t.encode("utf-8", errors="ignore")).hexdigest())
    )
    df = (
        df.drop_duplicates(subset="_hash", keep="first")
        .drop(columns="_hash")
        .reset_index(drop=True)
    )
    dropped = before - len(df)
    if dropped:
        print(f"  🔄 Global dedup removed {dropped} cross-source duplicates")
    return df


def stratified_split(
    df: pd.DataFrame,
    downsample_to: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split into train/val/test with stratification by label + source type.

    Manual implementation avoiding sklearn dependency (slow on Python 3.14).
    """

    # Optional: cap each class at downsample_to
    if downsample_to and downsample_to > 0:
        print(f"\n  📉 Downsampling each class to max {downsample_to}...")
        dfs_capped: list[pd.DataFrame] = []
        for label in sorted(df["label"].unique()):
            df_class = df[df["label"] == label]
            if len(df_class) > downsample_to:
                # Proportionally downsample real and synthetic
                real = df_class[~df_class["is_synthetic"]]
                synth = df_class[df_class["is_synthetic"]]

                real_target = min(
                    len(real), int(downsample_to * len(real) / len(df_class))
                )
                synth_target = downsample_to - real_target

                if real_target < len(real):
                    real = real.sample(n=real_target, random_state=RANDOM_STATE)
                if synth_target < len(synth):
                    synth = synth.sample(n=synth_target, random_state=RANDOM_STATE)

                df_class = pd.concat([real, synth], ignore_index=True)
                print(
                    f"    {LABEL_NAMES.get(label, label)}: capped to {len(df_class)} "
                    f"({len(real)} real + {len(synth)} synth)"
                )
            dfs_capped.append(df_class)
        df = pd.concat(dfs_capped, ignore_index=True)

    # Create stratification key: label + is_synthetic
    df = df.copy()
    df["_strat"] = df["label"].astype(str) + "_" + df["is_synthetic"].astype(str)

    # Manual stratified split: within each stratum, shuffle and assign rows
    train_parts: list[pd.DataFrame] = []
    val_parts: list[pd.DataFrame] = []
    test_parts: list[pd.DataFrame] = []

    for strat_key, group in df.groupby("_strat"):
        group_shuffled = group.sample(frac=1.0, random_state=RANDOM_STATE).reset_index(
            drop=True
        )
        n = len(group_shuffled)

        # Compute split indices
        n_test = max(1, round(n * TEST_RATIO))
        n_val = max(1, round(n * VAL_RATIO))
        n_train = n - n_val - n_test

        train_parts.append(group_shuffled.iloc[:n_train])
        val_parts.append(group_shuffled.iloc[n_train : n_train + n_val])
        test_parts.append(group_shuffled.iloc[n_train + n_val :])

    train_df = pd.concat(train_parts, ignore_index=True)
    val_df = pd.concat(val_parts, ignore_index=True)
    test_df = pd.concat(test_parts, ignore_index=True)

    # Drop helper columns
    for split_df in [train_df, val_df, test_df]:
        split_df.drop(columns=["_strat", "is_synthetic"], inplace=True)

    return (
        train_df.sample(frac=1.0, random_state=RANDOM_STATE).reset_index(drop=True),
        val_df.sample(frac=1.0, random_state=RANDOM_STATE).reset_index(drop=True),
        test_df.sample(frac=1.0, random_state=RANDOM_STATE).reset_index(drop=True),
    )


def save_split(df: pd.DataFrame, split_name: str) -> Path:
    """Save a split to data/final/{split}/."""
    out_dir = FINAL / split_name
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = f"sicurre_{split_name}.csv"
    out_path = out_dir / filename

    df[OUTPUT_COLS].to_csv(out_path, index=False)
    return out_path


def print_split_stats(df: pd.DataFrame, name: str) -> None:
    """Print class distribution for a split."""
    print(f"\n  📊 {name} split ({len(df)} rows):")
    for label in sorted(df["label"].unique()):
        count = len(df[df["label"] == label])
        label_name = LABEL_NAMES.get(label, f"label={label}")
        pct = count / len(df) * 100
        print(f"     {label_name:<12s} {count:>6d}  ({pct:.1f}%)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge processed CSVs into train/val/test splits"
    )
    parser.add_argument(
        "--downsample-to",
        "-d",
        type=int,
        default=0,
        help="Cap each class at this many rows (0 = no cap)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  SICURRE — Data Merge & Split")
    print(f"  Date: {TODAY}")
    print(f"  Split ratio: {TRAIN_RATIO:.0%} / {VAL_RATIO:.0%} / {TEST_RATIO:.0%}")
    print("=" * 60)

    # 1. Collect all CSVs
    print("\n📁 Collecting processed CSVs...")
    df = collect_csvs()
    print(f"\n  Total merged: {len(df)} rows")

    # 2. Global dedup
    print("\n🔄 Running global deduplication...")
    df = global_dedup(df)
    print(f"  After dedup: {len(df)} rows")

    # 3. Class distribution before split
    print("\n📈 Class distribution (before split):")
    for label in sorted(df["label"].unique()):
        count = len(df[df["label"] == label])
        real = len(df[(df["label"] == label) & (~df["is_synthetic"])])
        synth = count - real
        label_name = LABEL_NAMES.get(label, f"label={label}")
        print(
            f"  {label_name:<12s} {count:>6d}  (real={real}, synth={synth}, "
            f"real%={real/count*100:.0f}%)"
        )

    # 4. Stratified split
    print("\n✂️  Performing stratified split...")
    downsample = args.downsample_to if args.downsample_to > 0 else None
    train_df, val_df, test_df = stratified_split(df, downsample_to=downsample)

    # 5. Save splits
    print("\n💾 Saving splits...")
    for split_name, split_df in [
        ("train", train_df),
        ("val", val_df),
        ("test", test_df),
    ]:
        path = save_split(split_df, split_name)
        print_split_stats(split_df, split_name)
        print(f"     → {path.relative_to(BASE)}")

    # 6. Summary
    total = len(train_df) + len(val_df) + len(test_df)
    print(f"\n{'='*60}")
    print(f"  TOTAL: {total} rows")
    print(f"  Train: {len(train_df)} ({len(train_df)/total*100:.1f}%)")
    print(f"  Val:   {len(val_df)} ({len(val_df)/total*100:.1f}%)")
    print(f"  Test:  {len(test_df)} ({len(test_df)/total*100:.1f}%)")
    print(f"{'='*60}")
    print("  Done! 🎉")


if __name__ == "__main__":
    main()
