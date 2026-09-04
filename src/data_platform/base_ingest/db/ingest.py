"""Base ingestion for the External DB source — deterministic one-time population.

Downloads the canonical external_threats.db from Cloudflare R2 at:

    raw-snapshots/base/database/external_threats.db

Then runs LegacyDbIngestionService (NoOpSnapshotStore) to transfer all rows
from the temp DB into sicurre.db via proper DataRawRecord lineage.

Key properties:
- Deterministic: the R2 DB is the canonical seeded snapshot (seed=42)
- Idempotent: run twice → second run reports 0 new records (record_key dedup)
- No R2 writes (NoOpSnapshotStore)
- Re-seeding disabled by default; set SICURRE_DB_INGEST_FORCE_RESEED=true to
  re-generate the DB from archetypes and re-upload to R2 manually

Must be run AFTER sap-ingest-base (DB already contains 163,477 records).
PRIOR_RECORD_COUNT reflects the cumulative count after SAP Labs ingestion.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[4]  # repo root
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.config import get_settings, redact_database_url  # noqa: E402
from core.database import Base  # noqa: E402
from data_platform.extractors.legacy_db import (  # noqa: E402
    LegacyDbConnector,
    LegacyDbIngestionResult,
    LegacyDbIngestionService,
)
from data_platform.services.database.seed import seed_external_database  # noqa: E402
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

R2_FEEDER_DB_KEY = "raw-snapshots/base/database/external_threats.db"
MANIFEST_DIR = ROOT_DIR / "data" / "local" / "base-manifest" / "db"
MANIFEST_PATH = MANIFEST_DIR / "db_base_ingest_manifest.json"

# Records in sicurre.db after SAP Labs base ingestion.
PRIOR_RECORD_COUNT = 163_477


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
            storage_uri=f"noop://db_historical/{object_key}",
            content_hash=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
            local_path=None,
        )


# ── Manifest ──────────────────────────────────────────────────────────────────


def _save_manifest(result: LegacyDbIngestionResult, feeder_db_sha256: str) -> None:
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "description": (
            "External DB base ingestion — adapted EN→FR phishing + synthetic "
            "phishing/spam/legitimate from R2 canonical external_threats.db (seed=42), "
            "transferred to sicurre.db via LegacyDbIngestionService. "
            "Replay with 'make db-ingest-base'."
        ),
        "feeder_db": f"r2://sicurre-raw/{R2_FEEDER_DB_KEY}",
        "feeder_db_sha256": feeder_db_sha256,
        "ingestion_run_id": result.ingestion_run_id,
        "source_system_id": result.source_system_id,
        "raw_record_count": result.raw_record_count,
        "skipped_count": result.skipped_count,
        "total_extracted_count": result.total_extracted_count,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    logger.info("Manifest saved → %s", MANIFEST_PATH.relative_to(ROOT_DIR))


# ── Report ─────────────────────────────────────────────────────────────────────


def _print_report(result: LegacyDbIngestionResult, prior: int) -> None:
    sep = "=" * 76
    print(f"\n{sep}")
    print("  EXTERNAL DB BASE INGESTION — REPORT")
    print(sep)
    print(f"  Ingestion run ID   : {result.ingestion_run_id}")
    print(f"  Total extracted    : {result.total_extracted_count}")
    print(f"  New records        : {result.raw_record_count}")
    print(f"  Skipped (existing) : {result.skipped_count}")
    print(sep)
    total_cumulative = prior + result.raw_record_count
    print(f"\n  Records before this run (after SAP Labs) : {prior:>7,}")
    print(f"  New records inserted this run            : {result.raw_record_count:>7,}")
    print(f"  Cumulative total in sicurre.db           : {total_cumulative:>7,}")
    print(f"\n  Manifest → {MANIFEST_PATH.relative_to(ROOT_DIR)}")
    print(sep)


# ── Main ───────────────────────────────────────────────────────────────────────


async def run_db_ingestion(db_path: Path) -> LegacyDbIngestionResult:
    settings = get_settings()
    logger.info("Using database: %s", redact_database_url(settings.data_platform_database_url))
    engine = create_async_engine(settings.data_platform_database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    connector = LegacyDbConnector(db_url=f"sqlite+aiosqlite:///{db_path}")
    service = LegacyDbIngestionService(
        connector=connector,
        snapshot_store=NoOpSnapshotStore(),
    )

    async with session_factory() as session:
        result: LegacyDbIngestionResult = await service.run(
            session, trigger_mode="manual"
        )

    await engine.dispose()
    return result


def run_base_ingestion() -> None:
    r2 = R2ReadClient()

    # Optional reseed: re-generate the DB from archetypes (requires LLM provider)
    force_reseed = (
        os.environ.get("SICURRE_DB_INGEST_FORCE_RESEED", "false").lower() == "true"
    )
    if force_reseed:
        logger.info(
            "SICURRE_DB_INGEST_FORCE_RESEED=true — re-seeding external_threats.db"
        )
        seed_external_database(seed=42)
        logger.warning(
            "Re-seeded DB is at the local default path. "
            "Upload it to R2 at %s manually before next run.",
            R2_FEEDER_DB_KEY,
        )
        raise SystemExit(
            "Reseed complete. Upload to R2, then re-run without FORCE_RESEED."
        )

    # 1. Download canonical feeder DB from R2 to a temp file
    logger.info("Downloading feeder DB from R2: %s", R2_FEEDER_DB_KEY)
    with r2.download_to_tempfile(R2_FEEDER_DB_KEY) as tmp_path:
        feeder_db_sha256 = hashlib.sha256(tmp_path.read_bytes()).hexdigest()
        logger.info(
            "Feeder DB downloaded: %.1f KB  sha256=%s…",
            tmp_path.stat().st_size / 1024,
            feeder_db_sha256[:16],
        )

        # 2. Ingest feeder DB into sicurre.db via LegacyDbIngestionService
        logger.info("Ingesting feeder DB into sicurre.db …")
        result = asyncio.run(run_db_ingestion(tmp_path))

    logger.info(
        "Ingestion complete: new=%d  skipped=%d  total_extracted=%d",
        result.raw_record_count,
        result.skipped_count,
        result.total_extracted_count,
    )

    # 3. Save manifest only when new records were inserted
    if result.raw_record_count > 0:
        _save_manifest(result, feeder_db_sha256)
    else:
        logger.info("No new records inserted — manifest left unchanged")

    # 4. Print summary
    _print_report(result, PRIOR_RECORD_COUNT)


if __name__ == "__main__":
    run_base_ingestion()
