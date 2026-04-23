"""CC R2 base freeze proof script.

Freezes the Common Crawl source in R2 and proves that re-running the pipeline
from those R2 objects alone produces the same fr_usable row count as sicurre.db.

DOES NOT modify any existing local files or existing R2 objects.
Writes only to NEW keys:
  • raw-snapshots/bigdata/common_crawl/raw/common_crawl_raw_30_20260228_000000.parquet
  • raw-snapshots/bigdata/common_crawl/fr_usable/common_crawl_fr_usable_28_20260228_000000.parquet
  • raw-snapshots/bigdata/common_crawl/quality/quality_report_20260228_000000.json
  • raw-snapshots/bigdata/common_crawl/fr_usable/common_crawl_fr_usable_base_proof_<N>_<ts>.parquet
  • raw-snapshots/bigdata/common_crawl/quality/quality_base_proof_<ts>.json

Pipeline logic (mirrors build_base_merged_snapshot.py):
  concat(R2 fr_usable per-run parquets  +  R2 raw/ parquets)
    → dedup by content_hash
    → text_length filter 100–10,000 chars
  Expected output: 4,149 rows (same as sicurre.db common-crawl-bigdata count).
"""

from __future__ import annotations

import io
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(
    0, str(ROOT_DIR / "scripts" / "data_platform" / "shared" / "r2_freeze_proof")
)
from _common import (  # noqa: E402
    build_s3_client,
    download_bytes,
    get_db_source_counts,
    key_exists,
    list_keys,
    sha256_bytes,
    upload_bytes,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

ENV_FILE = ROOT_DIR / ".env"
DB_PATH = ROOT_DIR / "data" / "local" / "sicurre.db"

CC_LOCAL_DIR = ROOT_DIR / "data" / "raw" / "bigdata" / "common_crawl"
CC_PREFIX = "raw-snapshots/bigdata/common_crawl"
RAW_PREFIX = f"{CC_PREFIX}/raw"
FR_PREFIX = f"{CC_PREFIX}/fr_usable"
QUALITY_PREFIX = f"{CC_PREFIX}/quality"

# Feb-28 local source files — the only extraction run NOT yet in R2 raw/
FEB28_RAW_CSV = CC_LOCAL_DIR / "common_crawl_all_30_20260228.csv"
FEB28_FR_CSV = CC_LOCAL_DIR / "common_crawl_fr_usable_28_20260228.csv"
FEB28_QUALITY_JSON = CC_LOCAL_DIR / "quality_report_20260228.json"
FEB28_TIMESTAMP = "20260228_000000"

TEXT_LENGTH_MIN = 100
TEXT_LENGTH_MAX = 10_000

DB_SOURCE_NAME = "common-crawl-bigdata"
DB_TARGET = 4_149


# ── Step 1: Upload Feb-28 ──────────────────────────────────────────────────────


def upload_feb28(s3: Any, bucket: str) -> dict[str, Any]:
    """Upload Feb-28 extraction to R2 raw/, fr_usable/, quality/ — idempotent."""
    uploads: list[dict] = []
    skipped: list[str] = []

    # raw parquet (convert from CSV)
    raw_key = f"{RAW_PREFIX}/common_crawl_raw_30_{FEB28_TIMESTAMP}.parquet"
    if key_exists(s3, bucket, raw_key):
        logger.info("SKIP (exists): %s", raw_key)
        skipped.append(raw_key)
    else:
        df = pd.read_csv(FEB28_RAW_CSV)
        buf = io.BytesIO()
        df.to_parquet(buf, index=False, engine="pyarrow")
        payload = buf.getvalue()
        upload_bytes(s3, bucket, raw_key, payload, "application/vnd.apache.parquet")
        logger.info("UPLOADED raw/%d rows → %s", len(df), raw_key)
        uploads.append({"key": raw_key, "rows": len(df)})

    # fr_usable parquet
    fr_key = f"{FR_PREFIX}/common_crawl_fr_usable_28_{FEB28_TIMESTAMP}.parquet"
    if key_exists(s3, bucket, fr_key):
        logger.info("SKIP (exists): %s", fr_key)
        skipped.append(fr_key)
    else:
        df = pd.read_csv(FEB28_FR_CSV)
        buf = io.BytesIO()
        df.to_parquet(buf, index=False, engine="pyarrow")
        payload = buf.getvalue()
        upload_bytes(s3, bucket, fr_key, payload, "application/vnd.apache.parquet")
        logger.info("UPLOADED fr_usable/%d rows → %s", len(df), fr_key)
        uploads.append({"key": fr_key, "rows": len(df)})

    # quality JSON (as-is)
    q_key = f"{QUALITY_PREFIX}/quality_report_{FEB28_TIMESTAMP}.json"
    if key_exists(s3, bucket, q_key):
        logger.info("SKIP (exists): %s", q_key)
        skipped.append(q_key)
    else:
        payload = FEB28_QUALITY_JSON.read_bytes()
        upload_bytes(s3, bucket, q_key, payload, "application/json")
        logger.info("UPLOADED quality → %s", q_key)
        uploads.append({"key": q_key})

    return {"uploaded": uploads, "skipped": skipped}


# ── Step 2a: Download R2 raw/ parquets ─────────────────────────────────────────


def download_raw_parquets(s3: Any, bucket: str) -> tuple[list[pd.DataFrame], list[str]]:
    raw_keys = [k for k in list_keys(s3, bucket, RAW_PREFIX) if k.endswith(".parquet")]
    frames: list[pd.DataFrame] = []
    for key in raw_keys:
        payload = download_bytes(s3, bucket, key)
        df = pd.read_parquet(io.BytesIO(payload))
        logger.info("raw/ %s: %d rows", key.split("/")[-1], len(df))
        frames.append(df)
    return frames, raw_keys


# ── Step 2b: Download R2 fr_usable/ per-run parquets ──────────────────────────


def download_per_run_fr_usable(
    s3: Any, bucket: str
) -> tuple[list[pd.DataFrame], list[str]]:
    """Download per-run fr_usable parquets — skip recovery_, base_, proof_ outputs."""
    all_keys = [k for k in list_keys(s3, bucket, FR_PREFIX) if k.endswith(".parquet")]
    per_run_keys = [
        k
        for k in all_keys
        if not any(tag in k.split("/")[-1] for tag in ("recovery_", "base_", "proof_"))
    ]
    frames: list[pd.DataFrame] = []
    for key in per_run_keys:
        payload = download_bytes(s3, bucket, key)
        df = pd.read_parquet(io.BytesIO(payload))
        logger.info("fr_usable/ per-run %s: %d rows", key.split("/")[-1], len(df))
        frames.append(df)
    return frames, per_run_keys


# ── Step 3: Apply pipeline filters ────────────────────────────────────────────


def build_base(
    raw_frames: list[pd.DataFrame],
    fr_frames: list[pd.DataFrame],
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Replicate build_base_merged_snapshot.py logic from R2 sources."""
    # fr_usable first (mirrors: recovery parquet + CSVs in original script)
    all_frames = fr_frames + raw_frames
    combined = pd.concat(all_frames, ignore_index=True)
    before_dedup = len(combined)

    combined = combined.drop_duplicates(subset=["content_hash"]).reset_index(drop=True)
    after_dedup = len(combined)

    if "language" in combined.columns:
        combined = combined[combined["language"] == "fr"]

    if "text_length" in combined.columns:
        combined = combined[
            combined["text_length"].between(TEXT_LENGTH_MIN, TEXT_LENGTH_MAX)
        ]
    elif "text" in combined.columns:
        combined = combined[
            combined["text"].str.len().between(TEXT_LENGTH_MIN, TEXT_LENGTH_MAX)
        ]

    stats = {
        "before_dedup": before_dedup,
        "after_dedup": after_dedup,
        "dedup_dropped": before_dedup - after_dedup,
        "after_text_filter": len(combined),
    }
    logger.info(
        "Pipeline: %d → dedup → %d → text_length_filter → %d",
        before_dedup,
        after_dedup,
        len(combined),
    )
    return combined, stats


# ── Step 4: Upload proof outputs ───────────────────────────────────────────────


def upload_proof(
    s3: Any,
    bucket: str,
    df: pd.DataFrame,
    timestamp: str,
    raw_keys: list[str],
    fr_keys: list[str],
    pipeline_stats: dict[str, int],
) -> dict[str, str]:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow")
    parquet_payload = buf.getvalue()
    parquet_key = (
        f"{FR_PREFIX}/common_crawl_fr_usable_base_proof_{len(df)}_{timestamp}.parquet"
    )
    upload_bytes(
        s3, bucket, parquet_key, parquet_payload, "application/vnd.apache.parquet"
    )
    logger.info("Uploaded proof parquet: %s", parquet_key)

    quality = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "r2_base_freeze_proof",
        "row_count": len(df),
        "pipeline_stats": pipeline_stats,
        "input_raw_keys": raw_keys,
        "input_fr_usable_keys": fr_keys,
        "label_distribution": (
            df["label"].value_counts().to_dict() if "label" in df.columns else {}
        ),
        "language_distribution": (
            df["language"].value_counts().to_dict() if "language" in df.columns else {}
        ),
        "output_parquet_key": parquet_key,
        "output_parquet_sha256": sha256_bytes(parquet_payload),
    }
    quality_payload = json.dumps(quality, ensure_ascii=False, indent=2).encode("utf-8")
    quality_key = f"{QUALITY_PREFIX}/quality_base_proof_{timestamp}.json"
    upload_bytes(s3, bucket, quality_key, quality_payload, "application/json")
    logger.info("Uploaded proof quality JSON: %s", quality_key)

    return {"parquet_key": parquet_key, "quality_key": quality_key}


# ── Orchestrator ───────────────────────────────────────────────────────────────


def run(s3: Any, bucket: str) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    print("\n" + "=" * 70)
    print("  [CC] STEP 1 — Upload Feb-28 run to R2 (if missing)")
    print("=" * 70)
    feb28 = upload_feb28(s3, bucket)

    print("\n" + "=" * 70)
    print("  [CC] STEP 2a — Download all R2 raw/ parquets")
    print("=" * 70)
    raw_frames, raw_keys = download_raw_parquets(s3, bucket)

    print("\n" + "=" * 70)
    print("  [CC] STEP 2b — Download R2 fr_usable/ per-run parquets")
    print("=" * 70)
    fr_frames, fr_keys = download_per_run_fr_usable(s3, bucket)

    print("\n" + "=" * 70)
    print("  [CC] STEP 3 — Rebuild base fr_usable from R2 sources")
    print("=" * 70)
    df_base, pipeline_stats = build_base(raw_frames, fr_frames)
    r2_count = len(df_base)

    print("\n" + "=" * 70)
    print("  [CC] STEP 4 — Upload proof outputs to R2")
    print("=" * 70)
    proof_keys = upload_proof(
        s3, bucket, df_base, timestamp, raw_keys, fr_keys, pipeline_stats
    )

    # Compare to sicurre.db
    db_counts = get_db_source_counts(DB_PATH)
    db_count = db_counts.get(DB_SOURCE_NAME, -1)
    match = r2_count == DB_TARGET
    db_match = r2_count == db_count if db_count >= 0 else None

    result: dict[str, Any] = {
        "source": "common-crawl",
        "r2_raw_files": len(raw_keys),
        "r2_fr_usable_files": len(fr_keys),
        "r2_derived_rows": r2_count,
        "db_target": DB_TARGET,
        "db_actual": db_count,
        "pipeline_stats": pipeline_stats,
        "feb28_upload": feb28,
        "proof_keys": proof_keys,
        "match_target": match,
        "match_db": db_match,
    }

    sep = "=" * 70
    print(f"\n{sep}")
    print("  [CC] PROOF REPORT")
    print(sep)
    print(f"  R2 raw/ parquets consumed      : {len(raw_keys)} files")
    print(f"  R2 fr_usable/ per-run consumed : {len(fr_keys)} files")
    print(f"  After concat                   : {pipeline_stats['before_dedup']:,} rows")
    print(f"  After dedup                    : {pipeline_stats['after_dedup']:,} rows")
    print(f"  After text-length filter       : {r2_count:,} rows")
    print(f"  Target (base_4149)             : {DB_TARGET:,}")
    status = "✓  PASS" if match else f"✗  FAIL  (delta = {r2_count - DB_TARGET:+d})"
    print(f"  R2-derived == target           : {status}")
    if db_count >= 0:
        db_status = "✓  PASS" if db_match else "✗  FAIL"
        print(f"  sicurre.db CC rows             : {db_count:,}  →  {db_status}")
    print(f"  Proof parquet                  : {proof_keys['parquet_key']}")
    print(sep)

    return result


def main() -> None:
    s3, bucket = build_s3_client(ENV_FILE)
    run(s3, bucket)


if __name__ == "__main__":
    main()
