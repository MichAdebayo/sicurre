"""Base ingestion for the External DB source — deterministic one-time population.

Seeds external_threats.db from three archetype-based generators (seed=42):
  1. Adapted EN→FR phishing  — FrenchCulturalAdaptationService (~varied count)
  2. Synthetic phishing      — SyntheticGenerationService ("phishing", 7500)
  3. Synthetic spam          — SyntheticGenerationService ("spam", 10000)
  4. Synthetic legitimate    — SyntheticGenerationService ("legitimate", 5000)

Then runs LegacyDbIngestionService (NoOpSnapshotStore) to transfer all rows
from external_threats.db into sicurre.db via proper DataRawRecord lineage.

Key properties:
- Deterministic: seed=42 throughout — same output on every replay
- Idempotent: run twice → second run reports 0 new records (record_key dedup)
- No R2 writes (NoOpSnapshotStore)
- external_threats.db is wiped and re-seeded on each run (seed_external_database
  deletes the file before creating it)

Must be run AFTER sap-ingest-base (DB already contains 163,477 records).
PRIOR_RECORD_COUNT reflects the cumulative count after SAP Labs ingestion.
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

ROOT_DIR = Path(__file__).resolve().parents[4]  # repo root
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.config import get_settings  # noqa: E402
from core.database import Base  # noqa: E402
from data_platform.extractors.legacy_db import (  # noqa: E402
    LegacyDbConnector,
    LegacyDbIngestionResult,
    LegacyDbIngestionService,
)
from data_platform.services.database.seed import seed_external_database  # noqa: E402
from data_platform.services.shared.snapshot_storage import (  # noqa: E402
    SnapshotWriteResult,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

FEEDER_DB_PATH = ROOT_DIR / "data" / "raw" / "db" / "external_threats.db"
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
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": (
            "External DB base ingestion — adapted EN→FR phishing + synthetic "
            "phishing/spam/legitimate seeded into external_threats.db (seed=42), "
            "then transferred to sicurre.db via LegacyDbIngestionService. "
            "Replay with 'make db-ingest-base'."
        ),
        "feeder_db": str(FEEDER_DB_PATH.relative_to(ROOT_DIR)),
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


async def run_db_ingestion() -> LegacyDbIngestionResult:
    settings = get_settings()
    logger.info("Using database: %s", settings.database_url)
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    connector = LegacyDbConnector()
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
    # 1. Seed external_threats.db (deterministic, deletes + recreates)
    logger.info("Step 1/2 — Seeding external_threats.db (seed=42) …")
    seed_external_database(seed=42)

    feeder_db_sha256 = hashlib.sha256(FEEDER_DB_PATH.read_bytes()).hexdigest()
    logger.info(
        "Feeder DB seeded: %.1f KB  sha256=%s…",
        FEEDER_DB_PATH.stat().st_size / 1024,
        feeder_db_sha256[:16],
    )

    # 2. Ingest feeder DB into sicurre.db via LegacyDbIngestionService
    logger.info("Step 2/2 — Ingesting feeder DB into sicurre.db …")
    result = asyncio.run(run_db_ingestion())

    logger.info(
        "Ingestion complete: new=%d  skipped=%d  total_extracted=%d",
        result.raw_record_count,
        result.skipped_count,
        result.total_extracted_count,
    )

    # 3. Save manifest
    _save_manifest(result, feeder_db_sha256)

    # 4. Print summary
    _print_report(result, PRIOR_RECORD_COUNT)


if __name__ == "__main__":
    run_base_ingestion()
