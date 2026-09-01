"""Base ingestion for SAP Labs — deterministic one-time population of sicurre.db.

Reads the 18 French phishing/legitimate emails from the canonical JSON snapshot
stored in Cloudflare R2 at:

    raw-snapshots/base/scraping/sap_labs/sap_labs_fr_emails_18.json

This script:
  1. Downloads the JSON from R2.
  2. Calls SapLabsIngestionService with an inline R2-backed scraper client
     and a NoOpSnapshotStore (no R2 write).
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

from core.config import get_settings, redact_database_url  # noqa: E402
from core.database import Base  # noqa: E402
from data_platform.extractors.sap_labs import (  # noqa: E402
    SapLabsIngestionResult,
    SapLabsIngestionService,
    SapLabsScraperClient,
)
from data_platform.services.shared.snapshot_storage import (  # noqa: E402
    SnapshotWriteResult,
)
from data_platform.services.shared.r2_read_client import R2ReadClient  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

R2_SAP_LABS_KEY = "raw-snapshots/base/scraping/sap_labs/sap_labs_fr_emails_18.json"
MANIFEST_DIR = ROOT_DIR / "data" / "local" / "base-manifest" / "scraping"
MANIFEST_PATH = MANIFEST_DIR / "sap_labs_base_ingest_manifest.json"

# Records in sicurre.db after CERT-FR base ingestion.
PRIOR_RECORD_COUNT = 163_459


# ── R2-backed scraper client ───────────────────────────────────────────────────


class _R2SapScraperClient(SapLabsScraperClient):
    """Inline scraper client that serves pre-downloaded email records from R2."""

    def __init__(self, emails: list[dict[str, Any]]) -> None:
        super().__init__(url=f"r2://sicurre-raw/{R2_SAP_LABS_KEY}")
        self._emails = emails

    async def fetch_entries(self) -> list[dict[str, Any]]:
        return self._emails


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


def _save_manifest(
    result: SapLabsIngestionResult, r2_sha256: str, email_ids: list[Any]
) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": (
            "SAP Labs base ingestion — 18 French phishing/legitimate emails "
            "read from R2. Replay with 'make sap-ingest-base'."
        ),
        "r2_key": R2_SAP_LABS_KEY,
        "source_sha256": r2_sha256,
        "ingestion_run_id": result.ingestion_run_id,
        "source_system_id": result.source_system_id,
        "raw_record_count": result.raw_record_count,
        "skipped_count": result.skipped_count,
        "total_scraped_count": result.total_scraped_count,
        "email_ids": email_ids,
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
    # 1. Download JSON from R2
    r2 = R2ReadClient()
    logger.info("Downloading SAP Labs JSON from R2: %s", R2_SAP_LABS_KEY)
    raw_bytes = r2.download_bytes(R2_SAP_LABS_KEY)
    r2_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    emails: list[dict[str, Any]] = json.loads(
        raw_bytes.decode("utf-8", errors="replace")
    ).get("emails", [])
    if not emails:
        raise RuntimeError(
            f"R2 object {R2_SAP_LABS_KEY!r} contained no 'emails' entries."
        )
    logger.info("R2 JSON contains %d emails", len(emails))

    # 2. DB setup
    settings = get_settings()
    logger.info("Using database: %s", redact_database_url(settings.data_platform_database_url))
    engine = create_async_engine(settings.data_platform_database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    # 3. Run ingestion (R2-backed scraper, NoOp snapshot store)
    service = SapLabsIngestionService(
        scraper_client=_R2SapScraperClient(emails),
        snapshot_store=NoOpSnapshotStore(),
    )

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
    email_ids = [e.get("id") for e in emails]
    _save_manifest(result, r2_sha256, email_ids)

    # 5. Print summary
    _print_report(result, PRIOR_RECORD_COUNT)


if __name__ == "__main__":
    asyncio.run(run_base_ingestion())
