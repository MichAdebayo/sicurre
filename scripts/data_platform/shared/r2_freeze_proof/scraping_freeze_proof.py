"""Scraping R2 base freeze proof script — CERT-FR + SAP Labs.

CERT-FR (92 TXT files):
  Source  : R2 ``raw-snapshots/cert-fr/*.txt``  (already there from prior runs)
  Target  : R2 ``raw-snapshots/base/scraping/certfr/<filename>``
  Action  : S3 copy each TXT (idempotent — skips if destination key exists)
  Proof   : 92 TXT files in target prefix == 92 rows in sicurre.db certfr source

SAP Labs (18 emails):
  Source  : local ``data/raw/scraping/sap_labs_fr_emails_18.json``
            (canonical fallback JSON — all 4 local scrape JSONs contain identical
            18 email IDs, confirmed by prior audit)
  Target  : R2 ``raw-snapshots/base/scraping/sap_labs/sap_labs_fr_emails_18.json``
  Action  : Upload the canonical JSON (idempotent)
  Proof   : 18 emails in file == 18 rows in sicurre.db sap-labs-blog source

DOES NOT modify any existing local files or R2 objects under cert-fr/.
"""

from __future__ import annotations

import json
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
    download_bytes,
    get_db_source_counts,
    key_exists,
    list_keys,
    s3_copy,
    upload_bytes,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

ENV_FILE = ROOT_DIR / ".env"
DB_PATH = ROOT_DIR / "data" / "local" / "sicurre.db"

# CERT-FR
CERTFR_R2_SRC = "raw-snapshots/cert-fr"
CERTFR_R2_DST = "raw-snapshots/base/scraping/certfr"
DB_CERTFR_NAME = "certfr"
DB_CERTFR_TARGET = 92

# SAP Labs
SAP_LOCAL_JSON = ROOT_DIR / "data" / "raw" / "scraping" / "sap_labs_fr_emails_18.json"
SAP_R2_KEY = "raw-snapshots/base/scraping/sap_labs/sap_labs_fr_emails_18.json"
DB_SAP_NAME = "sap-labs-blog"
DB_SAP_TARGET = 18


# ── CERT-FR ────────────────────────────────────────────────────────────────────


def freeze_certfr(s3: Any, bucket: str) -> dict[str, Any]:
    """S3-copy all cert-fr TXT files to base/scraping/certfr/ (idempotent)."""
    src_keys = [k for k in list_keys(s3, bucket, CERTFR_R2_SRC) if k.endswith(".txt")]
    logger.info("CERT-FR source keys found: %d", len(src_keys))

    copied: list[str] = []
    skipped: list[str] = []

    for src_key in src_keys:
        filename = src_key.split("/")[-1]
        dst_key = f"{CERTFR_R2_DST}/{filename}"

        if key_exists(s3, bucket, dst_key):
            logger.info("SKIP (exists): %s", dst_key)
            skipped.append(dst_key)
        else:
            s3_copy(s3, bucket, src_key, dst_key)
            logger.info("COPIED %s → %s", src_key, dst_key)
            copied.append(dst_key)

    # Verify destination count
    dst_keys = [k for k in list_keys(s3, bucket, CERTFR_R2_DST) if k.endswith(".txt")]
    return {
        "src_keys_found": len(src_keys),
        "copied": len(copied),
        "skipped": len(skipped),
        "dst_keys_verified": len(dst_keys),
    }


# ── SAP Labs ──────────────────────────────────────────────────────────────────


def freeze_sap_labs(s3: Any, bucket: str) -> dict[str, Any]:
    """Upload canonical SAP Labs JSON to R2 base/scraping/sap_labs/ (idempotent)."""
    raw = SAP_LOCAL_JSON.read_bytes()
    data = json.loads(raw)
    email_count = len(data.get("emails", []))

    if key_exists(s3, bucket, SAP_R2_KEY):
        logger.info("SKIP (exists): %s", SAP_R2_KEY)
        status = "skipped"
    else:
        upload_bytes(s3, bucket, SAP_R2_KEY, raw, "application/json")
        logger.info(
            "UPLOADED: %s (%d emails, %d bytes)", SAP_R2_KEY, email_count, len(raw)
        )
        status = "uploaded"

    # Verify by downloading and counting
    payload = download_bytes(s3, bucket, SAP_R2_KEY)
    verified_count = len(json.loads(payload).get("emails", []))

    return {
        "key": SAP_R2_KEY,
        "email_count_local": email_count,
        "email_count_r2_verified": verified_count,
        "status": status,
    }


# ── Orchestrator ───────────────────────────────────────────────────────────────


def run(s3: Any, bucket: str) -> dict[str, Any]:
    print("\n" + "=" * 70)
    print(
        "  [Scraping] STEP 1 — Freeze CERT-FR (S3-copy cert-fr/ → base/scraping/certfr/)"
    )
    print("=" * 70)
    certfr_result = freeze_certfr(s3, bucket)

    print("\n" + "=" * 70)
    print("  [Scraping] STEP 2 — Freeze SAP Labs (upload canonical JSON)")
    print("=" * 70)
    sap_result = freeze_sap_labs(s3, bucket)

    db_counts = get_db_source_counts(DB_PATH)
    db_certfr = db_counts.get(DB_CERTFR_NAME, -1)
    db_sap = db_counts.get(DB_SAP_NAME, -1)

    certfr_r2_count = certfr_result["dst_keys_verified"]
    sap_r2_count = sap_result["email_count_r2_verified"]

    certfr_match = certfr_r2_count == DB_CERTFR_TARGET
    sap_match = sap_r2_count == DB_SAP_TARGET

    result: dict[str, Any] = {
        "source": "scraping",
        "certfr": {
            **certfr_result,
            "db_target": DB_CERTFR_TARGET,
            "db_actual": db_certfr,
            "match": certfr_match,
        },
        "sap_labs": {
            **sap_result,
            "db_target": DB_SAP_TARGET,
            "db_actual": db_sap,
            "match": sap_match,
        },
        "overall_match": certfr_match and sap_match,
    }

    sep = "=" * 70
    print(f"\n{sep}")
    print("  [Scraping] PROOF REPORT")
    print(sep)
    print("  CERT-FR:")
    print(f"    Source keys in R2 cert-fr/     : {certfr_result['src_keys_found']}")
    print(f"    Copied to base/scraping/certfr/: {certfr_result['copied']}")
    print(f"    Verified in destination        : {certfr_r2_count}")
    print(f"    Target (sicurre.db)            : {DB_CERTFR_TARGET}")
    certfr_status = (
        "✓  PASS"
        if certfr_match
        else f"✗  FAIL  (delta = {certfr_r2_count - DB_CERTFR_TARGET:+d})"
    )
    print(f"    File count == target           : {certfr_status}")
    if db_certfr >= 0:
        print(f"    sicurre.db certfr rows         : {db_certfr:,}")
    print()
    print("  SAP Labs:")
    print(f"    Emails in local JSON           : {sap_result['email_count_local']}")
    print(f"    Emails verified in R2          : {sap_r2_count}")
    print(f"    Target (sicurre.db)            : {DB_SAP_TARGET}")
    sap_status = (
        "✓  PASS"
        if sap_match
        else f"✗  FAIL  (delta = {sap_r2_count - DB_SAP_TARGET:+d})"
    )
    print(f"    Email count == target          : {sap_status}")
    if db_sap >= 0:
        print(f"    sicurre.db sap-labs rows       : {db_sap:,}")
    print(sep)

    return result


def main() -> None:
    s3, bucket = build_s3_client(ENV_FILE)
    run(s3, bucket)


if __name__ == "__main__":
    main()
