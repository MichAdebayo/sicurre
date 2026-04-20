"""PhishTank R2 base freeze proof script.

Groups local PhishTank CSVs by extraction date, merges with R2 phishtank CSVs
for the same date, deduplicates per date bucket by ``phish_id``, and uploads
one canonical CSV per date to:
  raw-snapshots/base/api/phishtank/phishtank_base_<YYYYMMDD>.csv

Date extraction:
  • Filenames that contain a date (e.g. ``phishtank_20260418_*.csv``) → parsed
    from the filename directly.
  • ``phishing-tank.csv`` (no date in name) → macOS creation time via
    ``os.stat().st_birthtime``, formatted as YYYYMMDD.

R2 existing CSVs (``raw-snapshots/phishtank/*.csv``) are listed and date-parsed
from their key name. They are merged into the appropriate date bucket.

DOES NOT modify any existing local files or existing R2 objects.
Only writes to ``raw-snapshots/base/api/phishtank/`` (idempotent per date key).
"""

from __future__ import annotations

import io
import logging
import os
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

LOCAL_PHISHTANK_DIR = ROOT_DIR / "data" / "raw" / "api" / "phishtank"
R2_EXISTING_PREFIX = "raw-snapshots/phishtank"
R2_BASE_PREFIX = "raw-snapshots/base/api/phishtank"

DB_SOURCE_NAME = "phishtank-online-valid"
DB_TARGET = 829

_DATE_RE = re.compile(r"phishtank_(\d{8})_")


# ── Date helpers ───────────────────────────────────────────────────────────────


def _date_from_filename(path: Path) -> str:
    """Extract YYYYMMDD from filename, or fall back to macOS creation time."""
    m = _DATE_RE.search(path.name)
    if m:
        return m.group(1)
    # Undated file — use macOS st_birthtime (visible in Finder as Date Created)
    try:
        ts = os.stat(path).st_birthtime
    except AttributeError:
        ts = os.stat(path).st_ctime  # Linux fallback: change time
    return datetime.fromtimestamp(ts).strftime("%Y%m%d")


def _date_from_r2_key(key: str) -> str | None:
    """Extract YYYYMMDD from an R2 key, or None if not found."""
    m = _DATE_RE.search(key)
    return m.group(1) if m else None


# ── Collect files by date bucket ──────────────────────────────────────────────


def collect_local_buckets() -> dict[str, list[Path]]:
    """Group local CSV files by date. Skip the .json file."""
    buckets: dict[str, list[Path]] = {}
    for path in sorted(LOCAL_PHISHTANK_DIR.glob("*.csv")):
        date = _date_from_filename(path)
        buckets.setdefault(date, []).append(path)
    return buckets


def collect_r2_buckets(s3: Any, bucket: str) -> dict[str, list[str]]:
    """Group existing R2 phishtank CSV keys by date."""
    keys = [k for k in list_keys(s3, bucket, R2_EXISTING_PREFIX) if k.endswith(".csv")]
    buckets: dict[str, list[str]] = {}
    for key in keys:
        date = _date_from_r2_key(key)
        if date:
            buckets.setdefault(date, []).append(key)
        else:
            logger.warning("R2 key has no date: %s — skipped", key)
    return buckets


# ── Process one date bucket ───────────────────────────────────────────────────


def _load_local_csv_unique(paths: list[Path]) -> pd.DataFrame:
    """Load all CSVs for a date, dedup files by sha256, concat rows."""
    seen_sha: set[str] = set()
    frames: list[pd.DataFrame] = []
    for path in paths:
        h = sha256_bytes(path.read_bytes())
        if h in seen_sha:
            logger.info("  SKIP dup file (sha256): %s", path.name)
            continue
        seen_sha.add(h)
        df = pd.read_csv(path)
        logger.info("  LOCAL %s: %d rows (sha256 %s)", path.name, len(df), h[:8])
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _load_r2_csv_unique(s3: Any, bucket: str, keys: list[str]) -> pd.DataFrame:
    """Load R2 CSVs for a date, dedup by sha256, concat rows."""
    seen_sha: set[str] = set()
    frames: list[pd.DataFrame] = []
    for key in keys:
        payload = download_bytes(s3, bucket, key)
        h = sha256_bytes(payload)
        if h in seen_sha:
            logger.info("  SKIP dup R2 file (sha256): %s", key.split("/")[-1])
            continue
        seen_sha.add(h)
        df = pd.read_csv(io.BytesIO(payload))
        logger.info("  R2 %s: %d rows (sha256 %s)", key.split("/")[-1], len(df), h[:8])
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_canonical_csv(
    date: str,
    local_paths: list[Path],
    r2_keys: list[str],
    s3: Any,
    bucket: str,
) -> pd.DataFrame:
    """Merge all files for a date, dedup by phish_id."""
    logger.info(
        "Processing date bucket: %s (%d local, %d R2)",
        date,
        len(local_paths),
        len(r2_keys),
    )
    df_local = _load_local_csv_unique(local_paths)
    df_r2 = _load_r2_csv_unique(s3, bucket, r2_keys)

    frames = [f for f in [df_local, df_r2] if not f.empty]
    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(subset=["phish_id"]).reset_index(drop=True)
    logger.info(
        "  Date %s: %d rows → dedup by phish_id → %d unique",
        date,
        before,
        len(combined),
    )
    return combined


# ── Upload canonical CSVs ──────────────────────────────────────────────────────


def upload_canonical_csvs(
    s3: Any,
    bucket: str,
    date_frames: dict[str, pd.DataFrame],
) -> list[dict[str, Any]]:
    uploaded: list[dict[str, Any]] = []
    for date, df in sorted(date_frames.items()):
        if df.empty:
            logger.warning("Empty frame for date %s — skipped", date)
            continue
        key = f"{R2_BASE_PREFIX}/phishtank_base_{date}.csv"
        if key_exists(s3, bucket, key):
            logger.info("SKIP (exists): %s", key)
            uploaded.append({"key": key, "rows": len(df), "status": "skipped"})
            continue
        payload = df.to_csv(index=False).encode("utf-8")
        upload_bytes(s3, bucket, key, payload, "text/csv")
        logger.info("UPLOADED %s: %d rows (%d bytes)", key, len(df), len(payload))
        uploaded.append({"key": key, "rows": len(df), "status": "uploaded"})
    return uploaded


# ── Orchestrator ───────────────────────────────────────────────────────────────


def run(s3: Any, bucket: str) -> dict[str, Any]:
    print("\n" + "=" * 70)
    print("  [PhishTank] STEP 1 — Group local files by date")
    print("=" * 70)
    local_buckets = collect_local_buckets()
    for date, paths in sorted(local_buckets.items()):
        logger.info("Local date %s: %d files", date, len(paths))

    print("\n" + "=" * 70)
    print("  [PhishTank] STEP 2 — List R2 existing phishtank CSVs by date")
    print("=" * 70)
    r2_buckets = collect_r2_buckets(s3, bucket)
    for date, keys in sorted(r2_buckets.items()):
        logger.info("R2 date %s: %d files", date, len(keys))

    # Merge date buckets (union of local + R2 date keys)
    all_dates: set[str] = set(local_buckets) | set(r2_buckets)
    logger.info("Total date buckets: %s", sorted(all_dates))

    print("\n" + "=" * 70)
    print("  [PhishTank] STEP 3 — Build canonical CSV per date bucket")
    print("=" * 70)
    date_frames: dict[str, pd.DataFrame] = {}
    for date in sorted(all_dates):
        df = build_canonical_csv(
            date,
            local_paths=local_buckets.get(date, []),
            r2_keys=r2_buckets.get(date, []),
            s3=s3,
            bucket=bucket,
        )
        date_frames[date] = df

    print("\n" + "=" * 70)
    print("  [PhishTank] STEP 4 — Upload canonical CSVs to R2 base/api/phishtank/")
    print("=" * 70)
    upload_results = upload_canonical_csvs(s3, bucket, date_frames)

    # Count total unique phish_ids across all date frames
    all_frames = [df for df in date_frames.values() if not df.empty]
    if all_frames:
        combined_all = pd.concat(all_frames, ignore_index=True)
        total_unique = combined_all["phish_id"].nunique()
    else:
        total_unique = 0

    db_counts = get_db_source_counts(DB_PATH)
    db_count = db_counts.get(DB_SOURCE_NAME, -1)
    match = total_unique == DB_TARGET
    db_match = total_unique == db_count if db_count >= 0 else None

    result: dict[str, Any] = {
        "source": "phishtank",
        "date_buckets": len(all_dates),
        "canonical_csvs_uploaded": len(upload_results),
        "total_unique_phish_ids": total_unique,
        "db_target": DB_TARGET,
        "db_actual": db_count,
        "upload_results": upload_results,
        "match_target": match,
        "match_db": db_match,
    }

    sep = "=" * 70
    print(f"\n{sep}")
    print("  [PhishTank] PROOF REPORT")
    print(sep)
    print(f"  Date buckets processed          : {len(all_dates)}")
    print(f"  Canonical CSVs in R2 base/      : {len(upload_results)}")
    print(f"  Total unique phish_ids (merged) : {total_unique:,}")
    print(f"  Target (sicurre.db)             : {DB_TARGET:,}")
    status = "✓  PASS" if match else f"✗  FAIL  (delta = {total_unique - DB_TARGET:+d})"
    print(f"  Unique phish_ids == target      : {status}")
    if db_count >= 0:
        db_status = "✓  PASS" if db_match else "✗  FAIL"
        print(f"  sicurre.db phishtank rows       : {db_count:,}  →  {db_status}")
    print(sep)

    return result


def main() -> None:
    s3, bucket = build_s3_client(ENV_FILE)
    run(s3, bucket)


if __name__ == "__main__":
    main()
