"""Database source R2 base freeze proof script — external_threats.db.

Uploads the SQLite database file to R2:
  local  : data/raw/db/external_threats.db
  R2 key : raw-snapshots/base/database/external_threats.db

Proof: downloads the file back from R2, opens it as SQLite, counts rows across
all user tables, and compares to the sicurre.db database-source row count
(target: 24,900 rows across 10 faker/adapted sources).

DOES NOT modify any existing local files or R2 objects.
Upload is idempotent — skipped if the key already exists.
"""

from __future__ import annotations

import io
import logging
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(
    0, str(ROOT_DIR / "scripts" / "data_platform" / "shared" / "r2_freeze_proof")
)
from _common import (  # noqa: E402
    build_s3_client,
    download_bytes,
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

EXTERNAL_DB_LOCAL = ROOT_DIR / "data" / "raw" / "db" / "external_threats.db"
R2_KEY = "raw-snapshots/base/database/external_threats.db"

# Database-source names in sicurre.db (all from external_threats.db)
DB_DATABASE_SOURCES = {
    "database/faker/synthetic_spam_simple": 3_000,
    "database/faker/synthetic_phishing_hard": 2_250,
    "database/faker/synthetic_legitimate_medium": 2_000,
    "database/adapted/adapted_en_fr": 2_400,
    "database/faker/synthetic_legitimate_hard": 1_500,
    "database/faker/synthetic_spam_hard": 3_000,
    "database/faker/synthetic_phishing_simple": 2_250,
    "database/faker/synthetic_spam_medium": 4_000,
    "database/faker/synthetic_phishing_medium": 3_000,
    "database/faker/synthetic_legitimate_simple": 1_500,
}
DB_DATABASE_TARGET = sum(DB_DATABASE_SOURCES.values())  # 24,900


def _count_external_db_tables(db_bytes: bytes) -> dict[str, int]:
    """Open a SQLite DB from bytes, return {table_name: row_count}."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(db_bytes)
        tmp_path = tmp.name

    conn = sqlite3.connect(tmp_path)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        counts: dict[str, int] = {}
        for table in tables:
            cnt = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[
                0
            ]  # noqa: S608
            counts[table] = cnt
        return counts
    finally:
        conn.close()
        Path(tmp_path).unlink(missing_ok=True)


def run(s3: Any, bucket: str) -> dict[str, Any]:
    print("\n" + "=" * 70)
    print("  [Database] STEP 1 — Upload external_threats.db to R2 base/database/")
    print("=" * 70)

    local_bytes = EXTERNAL_DB_LOCAL.read_bytes()
    file_size_mb = len(local_bytes) / (1024 * 1024)
    logger.info("Local file size: %.2f MB", file_size_mb)

    if key_exists(s3, bucket, R2_KEY):
        logger.info("SKIP (exists): %s", R2_KEY)
        upload_status = "skipped"
    else:
        upload_bytes(s3, bucket, R2_KEY, local_bytes, "application/octet-stream")
        logger.info("UPLOADED: %s (%.2f MB)", R2_KEY, file_size_mb)
        upload_status = "uploaded"

    print("\n" + "=" * 70)
    print("  [Database] STEP 2 — Verify by downloading from R2 and counting rows")
    print("=" * 70)
    r2_bytes = download_bytes(s3, bucket, R2_KEY)
    table_counts = _count_external_db_tables(r2_bytes)
    logger.info("Tables found in R2 DB: %d", len(table_counts))
    for table, cnt in sorted(table_counts.items()):
        logger.info("  %s: %d rows", table, cnt)

    r2_total = table_counts.get("threat_log", sum(table_counts.values()))

    db_counts = get_db_source_counts(DB_PATH)
    db_database_total = sum(db_counts.get(name, 0) for name in DB_DATABASE_SOURCES)
    total_match = r2_total == DB_DATABASE_TARGET
    db_match = r2_total == db_database_total if db_database_total > 0 else None

    result: dict[str, Any] = {
        "source": "database",
        "upload_status": upload_status,
        "file_size_mb": round(file_size_mb, 2),
        "r2_key": R2_KEY,
        "r2_table_counts": table_counts,
        "r2_total_rows": r2_total,
        "db_database_target": DB_DATABASE_TARGET,
        "db_database_actual": db_database_total,
        "match_target": total_match,
        "match_db": db_match,
    }

    sep = "=" * 70
    print(f"\n{sep}")
    print("  [Database] PROOF REPORT")
    print(sep)
    print(f"  Local file size                : {file_size_mb:.2f} MB")
    print(f"  Upload status                  : {upload_status}")
    print(f"  Tables in R2 DB                : {len(table_counts)}")
    print(f"  Total rows in R2 DB            : {r2_total:,}")
    print(f"  Target (sum of DB sources)     : {DB_DATABASE_TARGET:,}")
    status = (
        "✓  PASS"
        if total_match
        else f"✗  FAIL  (delta = {r2_total - DB_DATABASE_TARGET:+d})"
    )
    print(f"  R2 DB total == target          : {status}")
    if db_database_total > 0:
        db_status = "✓  PASS" if db_match else "✗  FAIL"
        print(
            f"  sicurre.db database rows       : {db_database_total:,}  →  {db_status}"
        )
    print()
    print("  Table breakdown (from R2):")
    for table, cnt in sorted(table_counts.items()):
        print(f"    {table:<45} {cnt:>8,}")
    print(sep)

    return result


def main() -> None:
    s3, bucket = build_s3_client(ENV_FILE)
    run(s3, bucket)


if __name__ == "__main__":
    main()
