"""Base ingestion for SAP Labs — deterministic one-time population of sicurre.db.

The SAP Labs dataset is a curated set of 18 French phishing/legitimate emails
published in a SAP community blog post and extracted into a local JSON file:

    data/raw/scraping/sap_labs_fr_emails_18.json

Seven snapshot files exist (3 in R2, 4 local, 1 fallback JSON) but all contain
the same 18 email IDs — confirmed by cross-inventory.  The canonical data is
the fallback JSON used by SapLabsIngestionService when the live blog is blocked.

This script:
  1. Calls SapLabsIngestionService with a NoOpSnapshotStore (no R2 write).
  2. The service reads its fallback JSON and inserts 18 new records.
  3. Writes a manifest to data/local/sap_labs_base_ingest_manifest.json.

Must be run AFTER certfr-ingest-base (DB contains ~163,459 records).
PRIOR_RECORD_COUNT reflects the cumulative count after CERT-FR ingestion.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[5]  # repo root
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.config import get_settings  # noqa: E402
from core.database import Base  # noqa: E402
from data_platform.extractors.sap_labs import (  # noqa: E402
    SapLabsIngestionResult,
    SapLabsIngestionService,
)
from data_platform.services.shared.snapshot_storage import (  # noqa: E402
    SnapshotWriteResult,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

FALLBACK_JSON = ROOT_DIR / "data" / "raw" / "scraping" / "sap_labs_fr_emails_18.json"
MANIFEST_PATH = ROOT_DIR / "data" / "local" / "sap_labs_base_ingest_manifest.json"

# Records in sicurre.db after CERT-FR base ingestion.
PRIOR_RECORD_COUNT = 163_459


# ── NoOpSnapshotStore ──────────────────────────────────────────────────────────


class NoOpSnapshotStore:
    """Satisfies the SnapshotStore protocol without writing to disk or R2."""

    def build_object_key(self, *, source_prefix: str, filename: str) -> str:
        return f"{source_prefix}/{filename}"

    async def write_snapshot(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str,
    ) -> SnapshotWriteResult:
        return SnapshotWriteResult(
            storage_uri=f"noop://sap_labs/{object_key}",
            content_hash=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
            local_path=None,
        )


# ── Manifest ──────────────────────────────────────────────────────────────────


def _save_manifest(result: SapLabsIngestionResult) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    fallback_data = json.loads(FALLBACK_JSON.read_text(encoding="utf-8"))
    emails = fallback_data.get("emails", [])
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": (
            "SAP Labs base ingestion — 18 French phishing/legitimate emails "
            "from the SAP community blog fallback JSON. "
            "Replay with 'make sap-ingest-base'."
        ),
        "source_file": str(FALLBACK_JSON.relative_to(ROOT_DIR)),
        "source_sha256": hashlib.sha256(FALLBACK_JSON.read_bytes()).hexdigest(),
        "ingestion_run_id": result.ingestion_run_id,
        "source_system_id": result.source_system_id,
        "raw_record_count": result.raw_record_count,
        "skipped_count": result.skipped_count,
        "total_scraped_count": result.total_scraped_count,
        "email_ids": [e.get("id") for e in emails],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    logger.info("Manifest saved → %s", MANIFEST_PATH.relative_to(ROOT_DIR))


# ── Report ─────────────────────────────────────────────────────────────────────


def _print_report(result: SapLabsIngestionResult, prior: int) -> None:
    sep = "=" * 76
    print(f"\n{sep}")
    print("  SAP LABS BASE INGESTION — REPORT")
    print(sep)
    print(f"  Ingestion run ID   : {result.ingestion_run_id}")
    print(f"  Total scraped      : {result.total_scraped_count}")
    print(f"  New records        : {result.raw_record_count}")
    print(f"  Skipped (existing) : {result.skipped_count}")
    print(sep)
    total_cumulative = prior + result.raw_record_count
    print(f"\n  Records before this run (after CERT-FR) : {prior:>7,}")
    print(f"  New records inserted this run           : {result.raw_record_count:>7,}")
    print(f"  Cumulative total in sicurre.db          : {total_cumulative:>7,}")
    print(f"\n  Manifest → {MANIFEST_PATH.relative_to(ROOT_DIR)}")
    print(sep)


# ── Main ───────────────────────────────────────────────────────────────────────


async def run_base_ingestion() -> None:
    # 1. Verify fallback JSON exists
    if not FALLBACK_JSON.exists():
        raise FileNotFoundError(
            f"SAP Labs fallback JSON not found: {FALLBACK_JSON}\n"
            "Ensure data/raw/scraping/sap_labs_fr_emails_18.json is present."
        )
    fallback_emails = json.loads(FALLBACK_JSON.read_text(encoding="utf-8")).get(
        "emails", []
    )
    logger.info("Fallback JSON contains %d emails", len(fallback_emails))

    # 2. DB setup
    settings = get_settings()
    logger.info("Using database: %s", settings.database_url)
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    # 3. Run ingestion (NoOp snapshot store — no R2 writes)
    service = SapLabsIngestionService(snapshot_store=NoOpSnapshotStore())

    async with session_factory() as session:
        result: SapLabsIngestionResult = await service.run(
            session, trigger_mode="manual"
        )

    logger.info(
        "Ingestion complete: new=%d skipped=%d",
        result.raw_record_count,
        result.skipped_count,
    )

    await engine.dispose()

    # 4. Save manifest
    _save_manifest(result)

    # 5. Print summary
    _print_report(result, PRIOR_RECORD_COUNT)


if __name__ == "__main__":
    asyncio.run(run_base_ingestion())
