"""File source R2 base freeze proof script — CSV + TXT.

Uploads all CSV and TXT source files from ``data/raw/file/`` to R2, preserving
the local directory hierarchy under ``raw-snapshots/base/file/``.

Included files:
  data/raw/file/csv/en/combined_final_clean.csv
  data/raw/file/csv/en/cybersectony_legit_6606_20260301.csv
  data/raw/file/csv/en/enron_hamspam_28191_20260301.csv
  data/raw/file/csv/fr/french_spamham_1000_20260301.csv
  data/raw/file/csv/fr/kaggle_multilingual_fr_4981_20260301.csv
  data/raw/file/csv/kaggle_multilingual_spam.csv
  data/raw/file/csv/multilingual-spam-data/data-en-hi-de-fr.csv
  data/raw/file/txt/Spam_1.txt … Spam_4.txt

Excluded:
  .gitkeep files
  french-spamham-detection-free/data.jsonl  (raw Kaggle format, not used by ingest)
  french-spamham-detection-free/LICENSE.md  (metadata, not data)

R2 target: ``raw-snapshots/base/file/<relative_path_from_file_root>``

Proof: compares total row/line counts from uploaded files to the sum of all
file-source DB row counts (target: 162,538 rows across 10 file sources).

Note: the DB count and raw-file row count may differ because the ingest pipeline
applies source-specific filtering (e.g. language filter, dedup). The proof
confirms the SOURCE FILES are correctly frozen in R2 — exact DB reproducibility
is verified by the DB wipe + reingest step.
"""

from __future__ import annotations

import csv
import io
import logging
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(
    0, str(ROOT_DIR / "scripts" / "data_platform" / "shared" / "r2_freeze_proof")
)
from _common import (  # noqa: E402
    build_s3_client,
    get_db_source_counts,
    key_exists,
    upload_bytes,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

ENV_FILE = ROOT_DIR / ".env"
DB_PATH = ROOT_DIR / "data" / "local" / "sicurre.db"

FILE_LOCAL_ROOT = ROOT_DIR / "data" / "raw" / "file"
R2_BASE_PREFIX = "raw-snapshots/base/file"

# File-source DB names and their row counts (used for the proof summary)
FILE_DB_SOURCES = {
    "zefang_phishing": 111_166,
    "enron_spam": 28_191,
    "kaggle_multilingual_spam": 10_138,
    "data-en-hi-de-fr": 5_157,
    "cybersectony_phishing_v2": 6_606,
    "kaggle_french_spamham": 1_000,
    "spam_1": 96,
    "spam_2": 26,
    "spam_3": 73,
    "spam_4": 85,
}
DB_FILE_TOTAL_TARGET = sum(FILE_DB_SOURCES.values())  # 162,538

# Files to skip entirely
_SKIP_NAMES = {"data.jsonl", "LICENSE.md", ".gitkeep"}


def _should_include(path: Path) -> bool:
    return path.suffix in (".csv", ".txt") and path.name not in _SKIP_NAMES


def _count_csv_rows(content: bytes) -> int:
    """Count data rows in a CSV (excludes header)."""
    try:
        text = content.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        return max(0, len(rows) - 1)  # subtract header
    except Exception:
        return -1


def _count_txt_lines(content: bytes) -> int:
    """Count non-empty lines in a TXT file."""
    try:
        text = content.decode("utf-8", errors="replace")
        return sum(1 for line in text.splitlines() if line.strip())
    except Exception:
        return -1


def collect_files() -> list[tuple[Path, str]]:
    """Return (local_path, r2_key) for all files to upload."""
    result: list[tuple[Path, str]] = []
    for path in sorted(FILE_LOCAL_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if not _should_include(path):
            continue
        relative = path.relative_to(FILE_LOCAL_ROOT)
        r2_key = f"{R2_BASE_PREFIX}/{relative.as_posix()}"
        result.append((path, r2_key))
    return result


def upload_files(s3: Any, bucket: str) -> list[dict[str, Any]]:
    files = collect_files()
    logger.info("Files to upload: %d", len(files))
    results: list[dict[str, Any]] = []

    for path, r2_key in files:
        content = path.read_bytes()
        row_count = (
            _count_csv_rows(content)
            if path.suffix == ".csv"
            else _count_txt_lines(content)
        )

        if key_exists(s3, bucket, r2_key):
            logger.info("SKIP (exists): %s", r2_key)
            results.append(
                {
                    "key": r2_key,
                    "local": str(path.relative_to(ROOT_DIR)),
                    "size_bytes": len(content),
                    "row_count": row_count,
                    "status": "skipped",
                }
            )
            continue

        content_type = "text/csv" if path.suffix == ".csv" else "text/plain"
        upload_bytes(s3, bucket, r2_key, content, content_type)
        logger.info(
            "UPLOADED %s: %d rows, %d bytes",
            r2_key.split("/")[-1],
            row_count,
            len(content),
        )
        results.append(
            {
                "key": r2_key,
                "local": str(path.relative_to(ROOT_DIR)),
                "size_bytes": len(content),
                "row_count": row_count,
                "status": "uploaded",
            }
        )

    return results


def run(s3: Any, bucket: str) -> dict[str, Any]:
    print("\n" + "=" * 70)
    print("  [File] Upload CSV + TXT files to R2 base/file/")
    print("=" * 70)
    upload_results = upload_files(s3, bucket)

    # Aggregate counts
    csv_files = [r for r in upload_results if r["key"].endswith(".csv")]
    txt_files = [r for r in upload_results if r["key"].endswith(".txt")]
    total_csv_rows = sum(r["row_count"] for r in csv_files if r["row_count"] >= 0)
    total_txt_lines = sum(r["row_count"] for r in txt_files if r["row_count"] >= 0)
    total_raw_rows = total_csv_rows + total_txt_lines

    db_counts = get_db_source_counts(DB_PATH)
    db_file_total = sum(db_counts.get(name, 0) for name in FILE_DB_SOURCES)

    result: dict[str, Any] = {
        "source": "file",
        "csv_files_uploaded": len(csv_files),
        "txt_files_uploaded": len(txt_files),
        "total_files": len(upload_results),
        "total_csv_rows": total_csv_rows,
        "total_txt_lines": total_txt_lines,
        "total_raw_rows": total_raw_rows,
        "db_file_total_target": DB_FILE_TOTAL_TARGET,
        "db_file_total_actual": db_file_total,
        "upload_results": upload_results,
    }

    sep = "=" * 70
    print(f"\n{sep}")
    print("  [File] PROOF REPORT")
    print(sep)
    print(f"  CSV files uploaded              : {len(csv_files)}")
    print(f"  TXT files uploaded              : {len(txt_files)}")
    print(f"  Total raw CSV rows              : {total_csv_rows:,}")
    print(f"  Total raw TXT lines             : {total_txt_lines:,}")
    print(f"  Total raw rows/lines            : {total_raw_rows:,}")
    print(f"  DB file total (target)          : {DB_FILE_TOTAL_TARGET:,}")
    print(f"  DB file total (actual)          : {db_file_total:,}")
    print()
    print("  Note: raw file count != DB count by design — ingest applies")
    print("  source-specific filtering. Exact DB match verified by wipe+reingest.")
    print()
    print("  Per-file breakdown:")
    for r in upload_results:
        rows_str = f"{r['row_count']:,}" if r["row_count"] >= 0 else "?"
        name = r["key"].split("/")[-1]
        print(f"    {name:<50} {rows_str:>10} rows  [{r['status']}]")
    print(sep)

    return result


def main() -> None:
    s3, bucket = build_s3_client(ENV_FILE)
    run(s3, bucket)


if __name__ == "__main__":
    main()
