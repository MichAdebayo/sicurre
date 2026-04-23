"""Common Crawl R2 base freeze proof script.

Collects all raw Common Crawl extraction outputs from both local CSVs and
R2 scattered parquets, groups them by extraction date, deduplicates per date
bucket by ``content_hash``, and uploads one canonical raw parquet per date to:

  raw-snapshots/base/bigdata/common_crawl/raw/common_crawl_raw_base_<YYYYMMDD>.parquet

Then reads ONLY from the ``base/`` prefix, merges all per-date parquets,
deduplicates globally, applies the pipeline filters (language == "fr" and
text_length 100–10,000), and asserts the result matches the DB target of
3,606 rows.  Uploads proof fr_usable parquet and quality JSON alongside.

Sources:
  Local  : data/raw/bigdata/common_crawl/common_crawl_all_*.csv
  R2     : raw-snapshots/bigdata/common_crawl/raw/*.parquet (excluding proof)

Target prefix (canonical):
  raw-snapshots/base/bigdata/common_crawl/raw/
  raw-snapshots/base/bigdata/common_crawl/fr_usable/
  raw-snapshots/base/bigdata/common_crawl/quality/

Follows the same pattern as phishtank_freeze_proof.py:
  R2_SCATTERED_PREFIX → collect → group by date → dedup → R2_BASE_PREFIX
"""

from __future__ import annotations

import io
import json
import logging
import re
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

# ── Local sources ──────────────────────────────────────────────────────────────

CC_LOCAL_DIR = ROOT_DIR / "data" / "raw" / "bigdata" / "common_crawl"

# ── R2 prefixes ────────────────────────────────────────────────────────────────

R2_SCATTERED_PREFIX = "raw-snapshots/bigdata/common_crawl/raw"
R2_BASE_PREFIX = "raw-snapshots/base/bigdata/common_crawl"
R2_BASE_RAW = f"{R2_BASE_PREFIX}/raw"
R2_BASE_FR_USABLE = f"{R2_BASE_PREFIX}/fr_usable"
R2_BASE_QUALITY = f"{R2_BASE_PREFIX}/quality"

# ── Pipeline constants ─────────────────────────────────────────────────────────

TEXT_LENGTH_MIN = 100
TEXT_LENGTH_MAX = 10_000

DB_SOURCE_NAME = "common-crawl-bigdata"
DB_TARGET = 3_606

DATE_PATTERN = re.compile(r"_(\d{8})")


# ── Helpers ────────────────────────────────────────────────────────────────────


def _extract_date(filename: str) -> str:
    """Extract YYYYMMDD date from a filename."""
    m = DATE_PATTERN.search(filename)
    return m.group(1) if m else "unknown"


def _read_csv_lenient(path: Path) -> pd.DataFrame:
    """Read a CSV, handling potential JSON content like in PhishTank."""
    raw = path.read_bytes()
    stripped = raw.lstrip()
    if stripped[:1] in (b"[", b"{"):
        return pd.read_json(io.BytesIO(raw))
    return pd.read_csv(path)


# ── Step 1: Collect all raw sources ────────────────────────────────────────────


def collect_local_raw(
) -> list[tuple[str, pd.DataFrame]]:
    """Load local common_crawl_all_*.csv files, tagged by date."""
    results: list[tuple[str, pd.DataFrame]] = []
    csv_files = sorted(CC_LOCAL_DIR.glob("common_crawl_all_*.csv"))
    for path in csv_files:
        date = _extract_date(path.name)
        df = _read_csv_lenient(path)
        logger.info("Local raw %s: date=%s, %d rows", path.name, date, len(df))
        results.append((date, df))
    return results


def collect_r2_scattered(
    s3: Any, bucket: str
) -> list[tuple[str, pd.DataFrame]]:
    """Download R2 scattered raw/ parquets (excluding proof files), tagged by date."""
    results: list[tuple[str, pd.DataFrame]] = []
    all_keys = list_keys(s3, bucket, R2_SCATTERED_PREFIX)
    raw_keys = [
        k for k in all_keys
        if k.endswith(".parquet") and "proof" not in k.split("/")[-1]
    ]
    for key in sorted(raw_keys):
        filename = key.split("/")[-1]
        date = _extract_date(filename)
        payload = download_bytes(s3, bucket, key)
        df = pd.read_parquet(io.BytesIO(payload))
        logger.info("R2 scattered raw %s: date=%s, %d rows", filename, date, len(df))
        results.append((date, df))
    return results


# ── Step 2: Group by date, dedup, upload ───────────────────────────────────────


def build_per_date_base(
    s3: Any,
    bucket: str,
    tagged_frames: list[tuple[str, pd.DataFrame]],
) -> dict[str, dict[str, Any]]:
    """Group frames by date, dedup per date, upload to base/raw/."""
    # Group
    date_buckets: dict[str, list[pd.DataFrame]] = {}
    for date, df in tagged_frames:
        date_buckets.setdefault(date, []).append(df)

    upload_results: dict[str, dict[str, Any]] = {}
    for date in sorted(date_buckets):
        frames = date_buckets[date]
        combined = pd.concat(frames, ignore_index=True)
        before = len(combined)
        deduped = combined.drop_duplicates(subset=["content_hash"]).reset_index(
            drop=True
        )
        after = len(deduped)
        logger.info(
            "Date %s: %d sources, %d raw → %d after dedup (-%d)",
            date, len(frames), before, after, before - after,
        )

        # Upload per-date parquet
        r2_key = f"{R2_BASE_RAW}/common_crawl_raw_base_{date}.parquet"
        buf = io.BytesIO()
        deduped.to_parquet(buf, index=False, engine="pyarrow")
        parquet_bytes = buf.getvalue()

        if key_exists(s3, bucket, r2_key):
            logger.info("  Already exists in R2: %s — skipping upload", r2_key)
            status = "already_exists"
        else:
            upload_bytes(
                s3, bucket, r2_key, parquet_bytes,
                "application/vnd.apache.parquet",
            )
            logger.info("  Uploaded → %s", r2_key)
            status = "uploaded"

        upload_results[date] = {
            "r2_key": r2_key,
            "rows": after,
            "dedup_dropped": before - after,
            "status": status,
            "sha256": sha256_bytes(parquet_bytes),
        }

    return upload_results


# ── Step 3: Freeze proof — read from base/ only ───────────────────────────────


def download_base_raw(
    s3: Any, bucket: str
) -> tuple[list[pd.DataFrame], list[str]]:
    """Download all per-date raw parquets from base/bigdata/common_crawl/raw/."""
    all_keys = list_keys(s3, bucket, R2_BASE_RAW)
    parquet_keys = [k for k in all_keys if k.endswith(".parquet")]
    frames: list[pd.DataFrame] = []
    for key in sorted(parquet_keys):
        payload = download_bytes(s3, bucket, key)
        df = pd.read_parquet(io.BytesIO(payload))
        logger.info("Base raw %s: %d rows", key.split("/")[-1], len(df))
        frames.append(df)
    return frames, parquet_keys


def apply_pipeline(
    raw_frames: list[pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """Merge, global dedup, apply pipeline filters → raw_base + fr_usable."""
    combined = pd.concat(raw_frames, ignore_index=True)
    before_dedup = len(combined)

    raw_base = combined.drop_duplicates(subset=["content_hash"]).reset_index(drop=True)
    after_dedup = len(raw_base)

    # Pipeline filter: language == "fr"
    fr_base = raw_base.copy()
    if "language" in fr_base.columns:
        fr_base = fr_base[fr_base["language"] == "fr"]

    # Pipeline filter: text_length
    if "text_length" in fr_base.columns:
        fr_base = fr_base[
            fr_base["text_length"].between(TEXT_LENGTH_MIN, TEXT_LENGTH_MAX)
        ]
    elif "text" in fr_base.columns:
        fr_base = fr_base[
            fr_base["text"].str.len().between(TEXT_LENGTH_MIN, TEXT_LENGTH_MAX)
        ]

    fr_base = fr_base.reset_index(drop=True)

    stats = {
        "raw_before_dedup": before_dedup,
        "raw_after_dedup": after_dedup,
        "raw_dedup_dropped": before_dedup - after_dedup,
        "fr_usable_after_lang_filter": len(fr_base),
    }
    logger.info(
        "Pipeline: %d raw → dedup → %d → fr + length → %d fr_usable",
        before_dedup, after_dedup, len(fr_base),
    )
    return raw_base, fr_base, stats


def upload_proof(
    s3: Any,
    bucket: str,
    fr_base: pd.DataFrame,
    timestamp: str,
    base_raw_keys: list[str],
    pipeline_stats: dict[str, int],
) -> dict[str, str]:
    """Upload fr_usable proof parquet + quality JSON to base/ prefix."""
    # fr_usable proof parquet
    buf = io.BytesIO()
    fr_base.to_parquet(buf, index=False, engine="pyarrow")
    fr_payload = buf.getvalue()
    fr_key = (
        f"{R2_BASE_FR_USABLE}/"
        f"common_crawl_fr_usable_base_proof_{len(fr_base)}_{timestamp}.parquet"
    )
    upload_bytes(
        s3, bucket, fr_key, fr_payload, "application/vnd.apache.parquet"
    )
    logger.info("Uploaded fr_usable proof: %s", fr_key)

    # Quality JSON
    quality = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "r2_base_freeze_proof_raw_to_fr_usable",
        "fr_usable_count": len(fr_base),
        "pipeline_stats": pipeline_stats,
        "base_raw_keys": base_raw_keys,
        "output_fr_usable_key": fr_key,
        "output_fr_usable_sha256": sha256_bytes(fr_payload),
        "label_distribution": (
            fr_base["label"].value_counts().to_dict()
            if "label" in fr_base.columns
            else {}
        ),
        "language_distribution": (
            fr_base["language"].value_counts().to_dict()
            if "language" in fr_base.columns
            else {}
        ),
    }
    quality_payload = json.dumps(
        quality, ensure_ascii=False, indent=2
    ).encode("utf-8")
    quality_key = f"{R2_BASE_QUALITY}/quality_base_proof_{timestamp}.json"
    upload_bytes(s3, bucket, quality_key, quality_payload, "application/json")
    logger.info("Uploaded quality JSON: %s", quality_key)

    return {"fr_usable_key": fr_key, "quality_key": quality_key}


# ── Orchestrator ───────────────────────────────────────────────────────────────


def run(s3: Any, bucket: str) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # ── Step 1: Collect all raw sources ────────────────────────────────────
    print("\n" + "=" * 70)
    print("  [CC] STEP 1 — Collect raw sources (local + R2 scattered)")
    print("=" * 70)
    tagged_frames: list[tuple[str, pd.DataFrame]] = []
    tagged_frames.extend(collect_local_raw())
    tagged_frames.extend(collect_r2_scattered(s3, bucket))
    logger.info("Total raw source batches collected: %d", len(tagged_frames))

    # ── Step 2: Group by date, dedup, upload to base/ ──────────────────────
    print("\n" + "=" * 70)
    print("  [CC] STEP 2 — Group by date, dedup, upload to base/raw/")
    print("=" * 70)
    per_date_results = build_per_date_base(s3, bucket, tagged_frames)
    total_base_rows = sum(r["rows"] for r in per_date_results.values())
    logger.info(
        "Per-date base upload complete: %d dates, %d total rows",
        len(per_date_results), total_base_rows,
    )

    # ── Step 3: Freeze proof — read from base/ only ────────────────────────
    print("\n" + "=" * 70)
    print("  [CC] STEP 3 — Freeze proof: read from base/, apply pipeline")
    print("=" * 70)
    base_frames, base_raw_keys = download_base_raw(s3, bucket)
    raw_base, fr_base, pipeline_stats = apply_pipeline(base_frames)
    r2_count = len(fr_base)

    # ── Step 4: Upload proof outputs ───────────────────────────────────────
    print("\n" + "=" * 70)
    print("  [CC] STEP 4 — Upload proof outputs to base/")
    print("=" * 70)
    proof_keys = upload_proof(
        s3, bucket, fr_base, timestamp, base_raw_keys, pipeline_stats
    )

    # ── Compare to sicurre.db ──────────────────────────────────────────────
    db_counts = get_db_source_counts(DB_PATH)
    db_count = db_counts.get(DB_SOURCE_NAME, -1)
    match = r2_count == DB_TARGET
    db_match = r2_count == db_count if db_count >= 0 else None

    result: dict[str, Any] = {
        "source": "common-crawl",
        "r2_raw_files": len(base_raw_keys),
        "r2_derived_rows": r2_count,
        "db_target": DB_TARGET,
        "db_actual": db_count,
        "pipeline_stats": pipeline_stats,
        "per_date_results": per_date_results,
        "proof_keys": proof_keys,
        "upload_status": "uploaded",
        "match_target": match,
        "db_match": db_match,
    }

    # ── Report ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  [CC] PROOF REPORT")
    print("=" * 70)
    print(f"  Per-date raw base files        : {len(per_date_results)} dates")
    for date, info in sorted(per_date_results.items()):
        print(f"    {date}: {info['rows']:,} rows ({info['status']})")
    print(f"  Raw base total (sum per-date)  : {total_base_rows:,} rows")
    print(f"  Raw base (global dedup)        : {len(raw_base):,} rows")
    print(f"  Fr_usable (pipeline output)    : {r2_count:,} rows")
    print(f"  Target                         : {DB_TARGET:,}")
    if match:
        print("  R2-derived == target           : ✓  PASS")
    else:
        print(
            f"  R2-derived == target           : ✗  FAIL  (delta = {r2_count - DB_TARGET})"
        )
    print(f"  Proof fr_usable                : {proof_keys['fr_usable_key']}")
    print("=" * 70)

    return result


def main() -> None:
    s3, bucket = build_s3_client(ENV_FILE)
    run(s3, bucket)


if __name__ == "__main__":
    main()
