"""R2 Base Freeze — full proof orchestrator.

Runs all source freeze proof scripts in sequence and prints a final summary
table comparing R2-derived counts to current sicurre.db counts.

Usage:
  uv run python scripts/data_platform/shared/r2_freeze_proof/run_all.py

Or via Makefile:
  make r2-freeze-proof

BEFORE running:
  - sicurre.db must be populated (run all make *-ingest-base first)
  - R2 credentials must be set in .env

AFTER running successfully:
  - All source files exist in R2 under raw-snapshots/base/
  - Proof outputs exist in R2 (fr_usable/proof and quality/proof keys for CC)
  - You can safely wipe sicurre.db and re-run make *-ingest-base to verify
    deterministic reproduction of the same 192,526 rows

Sources processed (in order):
  1. file         — CSV + TXT files  (~162,538 rows)
  2. database     — external_threats.db  (24,900 rows)
  3. scraping     — CERT-FR + SAP Labs  (110 rows)
  4. phishtank    — dated canonical CSVs  (829 rows)
  5. common-crawl — R2-native base parquet  (4,149 rows)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[4]
_PROOF_DIR = ROOT_DIR / "scripts" / "data_platform" / "shared" / "r2_freeze_proof"
sys.path.insert(0, str(_PROOF_DIR))

from _common import build_s3_client, get_db_source_counts  # noqa: E402
import cc_freeze_proof  # noqa: E402
import database_freeze_proof  # noqa: E402
import file_freeze_proof  # noqa: E402
import phishtank_freeze_proof  # noqa: E402
import scraping_freeze_proof  # noqa: E402

ENV_FILE = ROOT_DIR / ".env"
DB_PATH = ROOT_DIR / "data" / "local" / "sicurre.db"

DB_TOTAL_TARGET = 192_526


def _yesno(v: bool | None) -> str:
    if v is True:
        return "✓ PASS"
    if v is False:
        return "✗ FAIL"
    return "n/a"


def print_summary(
    results: dict[str, dict[str, Any]], db_before: int, elapsed: float
) -> None:
    sep = "=" * 78
    print(f"\n\n{sep}")
    print("  R2 BASE FREEZE — FINAL PROOF SUMMARY")
    print(sep)
    print(f"  sicurre.db BEFORE freeze       : {db_before:,} rows")
    print()
    print(f"  {'Source':<22} {'R2 count':>12}  {'DB target':>10}  {'Match':>12}")
    print(f"  {'-'*22} {'-'*12}  {'-'*10}  {'-'*12}")

    # CC
    cc = results.get("cc", {})
    print(
        f"  {'common-crawl':<22} {cc.get('r2_derived_rows', '?'):>12,}  "
        f"{cc.get('db_target', '?'):>10,}  {_yesno(cc.get('match_target')):>12}"
    )

    # PhishTank
    pt = results.get("phishtank", {})
    print(
        f"  {'phishtank':<22} {pt.get('total_unique_phish_ids', '?'):>12,}  "
        f"{pt.get('db_target', '?'):>10,}  {_yesno(pt.get('match_target')):>12}"
    )

    # Scraping
    sc = results.get("scraping", {})
    sc_certfr = sc.get("certfr", {})
    sc_sap = sc.get("sap_labs", {})
    print(
        f"  {'scraping/certfr':<22} {sc_certfr.get('dst_keys_verified', '?'):>12,}  "
        f"{sc_certfr.get('db_target', '?'):>10,}  {_yesno(sc_certfr.get('match')):>12}"
    )
    print(
        f"  {'scraping/sap_labs':<22} {sc_sap.get('email_count_r2_verified', '?'):>12,}  "
        f"{sc_sap.get('db_target', '?'):>10,}  {_yesno(sc_sap.get('match')):>12}"
    )

    # File
    fi = results.get("file", {})
    print(
        f"  {'file (raw rows)':<22} {fi.get('total_raw_rows', '?'):>12,}  "
        f"{fi.get('db_file_total_target', '?'):>10,}  {'(see note)':>12}"
    )

    # Database
    db = results.get("database", {})
    print(
        f"  {'database':<22} {db.get('r2_total_rows', '?'):>12,}  "
        f"{db.get('db_database_target', '?'):>10,}  {_yesno(db.get('match_target')):>12}"
    )

    print()

    all_matched = all(
        [
            cc.get("match_target"),
            pt.get("match_target"),
            sc_certfr.get("match"),
            sc_sap.get("match"),
            db.get("match_target"),
        ]
    )
    overall = (
        "✓  ALL COUNTABLE SOURCES MATCH"
        if all_matched
        else "✗  SOME SOURCES HAVE DELTA — CHECK ABOVE"
    )
    print(f"  Overall result                 : {overall}")
    print(f"  Elapsed                        : {elapsed:.1f}s")
    print()
    print("  Next step: wipe sicurre.db and run make *-ingest-base to confirm")
    print("  deterministic reproduction of 192,526 rows from R2 base/ alone.")
    print(sep)


def main() -> None:
    s3, bucket = build_s3_client(ENV_FILE)

    # Record DB state before freeze
    db_counts = get_db_source_counts(DB_PATH)
    db_before = sum(db_counts.values())
    print(
        f"\nsicurre.db current total: {db_before:,} rows  (target: {DB_TOTAL_TARGET:,})"
    )

    results: dict[str, Any] = {}
    t0 = time.time()

    results["file"] = file_freeze_proof.run(s3, bucket)
    results["database"] = database_freeze_proof.run(s3, bucket)
    results["scraping"] = scraping_freeze_proof.run(s3, bucket)
    results["phishtank"] = phishtank_freeze_proof.run(s3, bucket)
    results["cc"] = cc_freeze_proof.run(s3, bucket)

    elapsed = time.time() - t0
    print_summary(results, db_before, elapsed)


if __name__ == "__main__":
    main()
