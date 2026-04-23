"""Build the canonical Common Crawl base parquet for base ingestion.

Merges the two sources of local Common Crawl data:
  1. Latest recovery parquet in data/raw/bigdata/common_crawl/fr_usable/
     (already combines both R2 objects: 2358 + 1220 = 3578 unique rows)
  2. Legacy local CSVs in data/raw/bigdata/common_crawl/*.csv
     (4 files; 571 rows not already in the recovery parquet)

Deduplication key: ``content_hash`` (consistent across all sources).
Text-length filter: 100–10 000 chars (same gate as LocalCommonCrawlClient).

Output:
  data/raw/bigdata/common_crawl/fr_usable/
      common_crawl_fr_usable_base_<N>_<timestamp>.parquet

  data/raw/bigdata/common_crawl/quality/
      base_merge_manifest_<timestamp>.json

LocalCommonCrawlClient sorts fr_usable/ by mtime and picks the newest
parquet, so the output file automatically becomes the base-ingest input.

Run via:
  make bigdata-ingest-base   (called as step 1 of 2)
  or directly:
  uv run python scripts/data_platform/common_crawl/ingestion/build_base_merged_snapshot.py
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────

CC_DIR = ROOT_DIR / "data" / "raw" / "bigdata" / "common_crawl"
FR_USABLE_DIR = CC_DIR / "fr_usable"
QUALITY_DIR = CC_DIR / "quality"

TEXT_LENGTH_MIN = 100
TEXT_LENGTH_MAX = 10_000


# ── Helpers ────────────────────────────────────────────────────────────────────


def _load_latest_recovery_parquet() -> tuple[pd.DataFrame, Path]:
    parquet_files = sorted(
        FR_USABLE_DIR.glob("*.parquet"),
        key=lambda p: p.stat().st_mtime,
    )
    if not parquet_files:
        raise FileNotFoundError(f"No .parquet files found in {FR_USABLE_DIR}")
    latest = parquet_files[-1]
    logger.info("Recovery parquet: %s", latest.name)
    df = pd.read_parquet(latest)
    logger.info("  → %d rows", len(df))
    return df, latest


def _load_legacy_csvs() -> pd.DataFrame:
    csv_files = sorted(CC_DIR.glob("*fr_usable*.csv"))
    if not csv_files:
        logger.info("No legacy fr_usable CSVs found in %s — skipping", CC_DIR)
        return pd.DataFrame()
    frames: list[pd.DataFrame] = []
    for path in csv_files:
        df = pd.read_csv(path)
        logger.info("CSV %s: %d rows", path.name, len(df))
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _apply_text_length_filter(df: pd.DataFrame) -> pd.DataFrame:
    if "text_length" in df.columns:
        before = len(df)
        df = df[df["text_length"].between(TEXT_LENGTH_MIN, TEXT_LENGTH_MAX)]
        dropped = before - len(df)
        if dropped:
            logger.info("Text-length filter removed %d rows", dropped)
    elif "text" in df.columns:
        before = len(df)
        df = df[df["text"].str.len().between(TEXT_LENGTH_MIN, TEXT_LENGTH_MAX)]
        dropped = before - len(df)
        if dropped:
            logger.info("Text-length filter (computed) removed %d rows", dropped)
    return df


# ── Main ───────────────────────────────────────────────────────────────────────


def build_base_snapshot() -> Path:
    FR_USABLE_DIR.mkdir(parents=True, exist_ok=True)
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load recovery parquet (R2 combined)
    df_parquet, parquet_source = _load_latest_recovery_parquet()

    # 2. Load legacy CSVs
    df_csv = _load_legacy_csvs()

    # 3. Combine and deduplicate by content_hash
    if not df_csv.empty:
        combined = pd.concat([df_parquet, df_csv], ignore_index=True)
    else:
        combined = df_parquet.copy()

    before_dedup = len(combined)
    combined = combined.drop_duplicates(subset=["content_hash"]).reset_index(drop=True)
    dedup_dropped = before_dedup - len(combined)
    logger.info(
        "After dedup by content_hash: %d rows (%d duplicates removed)",
        len(combined),
        dedup_dropped,
    )

    # 4. Text-length filter
    combined = _apply_text_length_filter(combined)
    logger.info("Final row count after text-length filter: %d", len(combined))

    # 5. Save output parquet
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = (
        FR_USABLE_DIR
        / f"common_crawl_fr_usable_base_{len(combined)}_{timestamp}.parquet"
    )
    combined.to_parquet(output_path, index=False, engine="pyarrow")
    logger.info("Base parquet saved → %s", output_path.relative_to(ROOT_DIR))

    # 6. Write manifest
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "base_merge",
        "recovery_parquet": str(parquet_source.relative_to(ROOT_DIR)),
        "legacy_csv_count": len(df_csv) if not df_csv.empty else 0,
        "rows_before_dedup": before_dedup,
        "dedup_dropped": dedup_dropped,
        "rows_after_dedup": len(combined)
        + (before_dedup - len(combined) - dedup_dropped),
        "final_row_count": len(combined),
        "output_parquet": str(output_path.relative_to(ROOT_DIR)),
    }
    # recalculate cleanly
    manifest["rows_after_dedup"] = before_dedup - dedup_dropped

    manifest_path = QUALITY_DIR / f"base_merge_manifest_{timestamp}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    logger.info("Manifest saved → %s", manifest_path.relative_to(ROOT_DIR))

    sep = "=" * 72
    print(f"\n{sep}")
    print("  COMMON CRAWL BASE MERGE — REPORT")
    print(sep)
    print(f"  Recovery parquet  : {parquet_source.name}  ({len(df_parquet):,} rows)")
    print(f"  Legacy CSV rows   : {len(df_csv) if not df_csv.empty else 0:,}")
    print(f"  After concat      : {before_dedup:,}")
    print(f"  After dedup       : {before_dedup - dedup_dropped:,}")
    print(f"  After len filter  : {len(combined):,}")
    print(f"  Output parquet    : {output_path.relative_to(ROOT_DIR)}")
    print(sep)

    return output_path


if __name__ == "__main__":
    build_base_snapshot()
