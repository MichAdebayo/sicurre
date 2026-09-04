"""Base ingestion for the Common Crawl bigdata source — deterministic one-time population.

Downloads the canonical base parquet from Cloudflare R2 under:

    raw-snapshots/base/bigdata/common_crawl/fr_usable/

Then ingests it into sicurre.db via CommonCrawlIngestionService with
LocalCommonCrawlClient pointed at the temporary download directory.

Key properties:
- LocalCommonCrawlClient reads the downloaded parquet from a temp dir.
- NoOpSnapshotStore is used — no R2 writes.
- Idempotent: if sicurre.db already has ≥ IDEMPOTENCY_THRESHOLD rows for the
  common-crawl-bigdata source, the run exits early without touching the DB.
- Manifest written only when raw_record_count > 0 (same guard as db-ingest-base).

Must be run AFTER db-ingest-base.
PRIOR_RECORD_COUNT reflects the cumulative count after db-ingest-base.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[5]  # repo root
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.config import get_settings, redact_database_url  # noqa: E402
from core.database import Base  # noqa: E402
from data_platform.extractors.common_crawl_ingestion import (  # noqa: E402
    CommonCrawlIngestionResult,
    CommonCrawlIngestionService,
    LocalCommonCrawlClient,
)
from data_platform.services.shared.r2_read_client import R2ReadClient  # noqa: E402
from data_platform.services.shared.snapshot_storage import (  # noqa: E402
    SnapshotWriteResult,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

SOURCE_NAME = "common-crawl-bigdata"
R2_CC_PREFIX = "raw-snapshots/base/bigdata/common_crawl/fr_usable"
MANIFEST_DIR = ROOT_DIR / "data" / "local" / "base-manifest" / "bigdata"
MANIFEST_PATH = MANIFEST_DIR / "cc_base_ingest_manifest.json"

# Records in sicurre.db after db-ingest-base (all prior sources).
PRIOR_RECORD_COUNT = 188_377

# If this many rows already exist for the CC source, skip re-ingestion.
IDEMPOTENCY_THRESHOLD = 4_000


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
            storage_uri=f"noop://common_crawl/{object_key}",
            content_hash=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
            local_path=None,
        )


# ── Idempotency guard ──────────────────────────────────────────────────────────


async def _existing_cc_record_count(engine) -> int:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT COUNT(r.id) FROM data_raw_record r "
                "JOIN data_source_system ss ON ss.id = r.source_system_id "
                "WHERE ss.name = :name"
            ),
            {"name": SOURCE_NAME},
        )
        return result.scalar() or 0


# ── Manifest ──────────────────────────────────────────────────────────────────


def _save_manifest(result: CommonCrawlIngestionResult) -> None:
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "description": (
            "Common Crawl base ingestion — merged R2 + legacy local CSVs "
            "(3606 unique fr rows by content_hash) ingested via LocalCommonCrawlClient. "
            "Replay with 'make bigdata-ingest-base'."
        ),
        "ingestion_run_id": result.ingestion_run_id,
        "source_system_id": result.source_system_id,
        "raw_record_count": result.raw_record_count,
        "skipped_count": result.skipped_count,
        "total_extracted_count": result.total_extracted_count,
        "snapshot_storage_uri": result.snapshot_storage_uri,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    logger.info("Manifest saved → %s", MANIFEST_PATH.relative_to(ROOT_DIR))


# ── Report ─────────────────────────────────────────────────────────────────────


def _print_report(result: CommonCrawlIngestionResult, prior: int) -> None:
    sep = "=" * 76
    print(f"\n{sep}")
    print("  COMMON CRAWL BASE INGESTION — REPORT")
    print(sep)
    print(f"  Ingestion run ID   : {result.ingestion_run_id}")
    print(f"  Total extracted    : {result.total_extracted_count}")
    print(f"  New records        : {result.raw_record_count}")
    print(f"  Skipped (existing) : {result.skipped_count}")
    print(sep)
    total_cumulative = prior + result.raw_record_count
    print(f"\n  Records before this run (after db-ingest-base) : {prior:>7,}")
    print(
        f"  New records inserted this run                  : {result.raw_record_count:>7,}"
    )
    print(f"  Cumulative total in sicurre.db                 : {total_cumulative:>7,}")
    print(f"\n  Manifest → {MANIFEST_PATH.relative_to(ROOT_DIR)}")
    print(sep)


# ── Main ───────────────────────────────────────────────────────────────────────


async def run_cc_ingestion(local_parquet_dir: Path) -> CommonCrawlIngestionResult:
    settings = get_settings()
    logger.info("Using database: %s", redact_database_url(settings.data_platform_database_url))
    engine = create_async_engine(settings.data_platform_database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Idempotency guard — skip if already populated
    existing = await _existing_cc_record_count(engine)
    if existing >= IDEMPOTENCY_THRESHOLD:
        logger.info(
            "sicurre.db already has %d rows for '%s' (threshold %d) — skipping re-ingest (idempotent)",
            existing,
            SOURCE_NAME,
            IDEMPOTENCY_THRESHOLD,
        )
        await engine.dispose()
        # Return a no-op result
        from data_platform.extractors.common_crawl_ingestion import (
            CommonCrawlIngestionResult,
        )

        return CommonCrawlIngestionResult(
            ingestion_run_id="skipped",
            source_system_id="skipped",
            snapshot_path=None,
            snapshot_storage_uri="",
            raw_object_count=0,
            raw_record_count=0,
            skipped_count=existing,
            total_extracted_count=existing,
            log_message=f"Idempotent skip: {existing} rows already present",
        )

    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    # Instantiate LocalCommonCrawlClient with the temp download directory
    local_client = LocalCommonCrawlClient(local_parquet_dir=local_parquet_dir)
    service = CommonCrawlIngestionService(
        bq_client=local_client,
        snapshot_store=NoOpSnapshotStore(),
    )

    async with session_factory() as session:
        result: CommonCrawlIngestionResult = await service.run(
            session, trigger_mode="base_ingest"
        )

    await engine.dispose()
    return result


def run_base_ingestion() -> None:
    r2 = R2ReadClient()

    # Find the most recent base-proof parquet under the R2 prefix
    objects = r2.list_objects(R2_CC_PREFIX, suffix=".parquet")
    proof_objects = [o for o in objects if "_base_proof_" in o.key]
    if not proof_objects:
        raise RuntimeError(
            f"No '_base_proof_' parquet found under R2 prefix {R2_CC_PREFIX!r}. "
            "Upload a base parquet before running this script."
        )
    # list_objects returns sorted by key; take the last (most recent by name sort)
    target_key = proof_objects[-1].key
    logger.info(
        "Using R2 parquet: %s (%d bytes)", target_key, proof_objects[-1].size_bytes
    )

    with r2.download_to_tempfile(target_key) as tmp_path:
        logger.info("Common Crawl base ingestion starting …")
        result = asyncio.run(run_cc_ingestion(tmp_path.parent))

    if result.ingestion_run_id == "skipped":
        _print_report(result, PRIOR_RECORD_COUNT)
        return

    logger.info(
        "Ingestion complete: new=%d  skipped=%d  total_extracted=%d",
        result.raw_record_count,
        result.skipped_count,
        result.total_extracted_count,
    )

    if result.raw_record_count > 0:
        _save_manifest(result)
    else:
        logger.info("No new records inserted — manifest left unchanged")

    _print_report(result, PRIOR_RECORD_COUNT)


if __name__ == "__main__":
    run_base_ingestion()
