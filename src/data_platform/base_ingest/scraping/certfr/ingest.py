"""Base ingestion for CERT-FR — deterministic one-time population of sicurre.db.

Reads all frozen TXT snapshots from Cloudflare R2 under
``raw-snapshots/base/scraping/certfr/`` (sorted by key for reproducibility).

Label assignment (in-memory, no CSV):
  - ``CertFRCtiExtractor._classify_phishing_relevance(text, title)`` returns
    True  → "phishing"
  - Returns False → "legitimate"
  Title is extracted from the TXT content (the "Objet:" header line).

Each TXT file maps to:
  - 1 DataRawObject  (external_ref = certfr_id, content_hash = sha256(bytes))
  - 1 DataRawRecord  (record_key = sha256(text[:300]), raw_content = JSON)

The manifest is written to data/local/certfr_base_ingest_manifest.json before
any DB writes so replay provenance is always available.

Must be run AFTER file-ingest-base (DB already contains ~163,367 records).
PRIOR_RECORD_COUNT reflects the cumulative count after File source ingestion.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[5]  # repo root
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.config import get_settings  # noqa: E402
from core.database import Base  # noqa: E402
from db.models import (  # noqa: E402
    DataIngestionRun,
    DataRawObject,
    DataRawRecord,
    IngestionStatus,
    ObjectType,
)
from db.queries import IngestionRunQueries, SourceSystemQueries  # noqa: E402
from data_platform.api.schemas import DataSourceCreate, IngestionRunCreate  # noqa: E402
from data_platform.extractors.certfr_cti import CertFRCtiExtractor  # noqa: E402
from data_platform.services.shared.r2_read_client import R2ReadClient  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

R2_CERTFR_PREFIX = "raw-snapshots/base/scraping/certfr"
MANIFEST_PATH = ROOT_DIR / "data" / "local" / "certfr_base_ingest_manifest.json"

SOURCE_MACHINE_NAME = "cert-fr-cti"
SOURCE_DISPLAY_NAME = "CERT-FR CTI"
SOURCE_TYPE = "scraping"

CERTFR_REF_RE = re.compile(r"(CERTFR-\d{4}-(?:CTI|IOC)-\d+)", re.IGNORECASE)

# Records in sicurre.db after File source base ingestion.
PRIOR_RECORD_COUNT = 163_367


# ── Snapshot entry ─────────────────────────────────────────────────────────────


@dataclass
class _SnapshotEntry:
    sha256: str
    label: str  # always "r2"
    filename: str  # e.g. CERTFR-2019-CTI-001.pdf.txt
    certfr_id: str  # e.g. CERTFR-2019-CTI-001
    storage_uri: str  # r2:// or file://
    data: bytes
    size_bytes: int
    r2_key: str | None = None
    r2_etag: str | None = None


def _extract_certfr_id(filename: str) -> str:
    """Extract the CERTFR reference from a snapshot filename."""
    match = CERTFR_REF_RE.search(filename)
    if match:
        return match.group(1).upper()
    # Fallback: strip known extensions
    stem = filename
    for ext in (".pdf.txt", ".html.txt", ".txt"):
        if stem.lower().endswith(ext):
            stem = stem[: -len(ext)]
            break
    return stem.upper()


# ── R2 + local enumeration ─────────────────────────────────────────────────────


def _enumerate_r2_snapshots(r2: R2ReadClient) -> list[_SnapshotEntry]:
    """Download all TXT snapshots from R2 base prefix, sorted by key."""
    objects = r2.list_objects(R2_CERTFR_PREFIX, suffix=".txt")
    entries: list[_SnapshotEntry] = []
    for obj in objects:
        filename = obj.key.rsplit("/", 1)[-1]
        logger.info("Downloading R2: %s (%d bytes)", obj.key, obj.size_bytes)
        data = r2.download_bytes(obj.key)
        sha256 = hashlib.sha256(data).hexdigest()
        entries.append(
            _SnapshotEntry(
                sha256=sha256,
                label="r2",
                filename=filename,
                certfr_id=_extract_certfr_id(filename),
                storage_uri=f"r2://{r2.bucket}/{obj.key}",
                data=data,
                size_bytes=len(data),
                r2_key=obj.key,
                r2_etag=obj.etag,
            )
        )
    return entries


def _extract_title_from_text(text: str) -> str:
    """Extract the report title from the 'Objet:' header line in TXT content."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Objet:"):
            return stripped[len("Objet:") :].strip()
    return ""


def _derive_label_from_text(text: str, title: str) -> str:
    """Classify phishing relevance using the same logic as the live scraper."""
    is_phishing = CertFRCtiExtractor._classify_phishing_relevance(text, title)
    return "phishing" if is_phishing else "legitimate"


# ── Manifest ──────────────────────────────────────────────────────────────────


def _save_manifest(entries: list[_SnapshotEntry]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    snapshots = [
        {
            "source": "r2",
            "r2_key": e.r2_key,
            "r2_etag": e.r2_etag,
            "filename": e.filename,
            "certfr_id": e.certfr_id,
            "storage_uri": e.storage_uri,
            "sha256": e.sha256,
            "size_bytes": e.size_bytes,
        }
        for e in entries
    ]
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": (
            "R2-only CERT-FR TXT snapshots used for base ingestion. "
            "Replay with 'make certfr-ingest-base' on a DB that has already "
            "had phishtank-ingest-base and file-ingest-base applied."
        ),
        "selected_count": len(snapshots),
        "total_discovered": len(snapshots),
        "snapshots": snapshots,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    logger.info("Manifest saved → %s", MANIFEST_PATH.relative_to(ROOT_DIR))


# ── Source system helper ───────────────────────────────────────────────────────


async def _get_or_create_source_system(
    session: AsyncSession,
    source_repo: SourceSystemQueries,
) -> Any:
    existing = await source_repo.get_by_name(session, SOURCE_MACHINE_NAME)
    if existing:
        return existing
    return await source_repo.create(
        session,
        DataSourceCreate(
            name=SOURCE_MACHINE_NAME,
            source_type=SOURCE_TYPE,
            description="CERT-FR CTI and IOC reports scraped from cert.ssi.gouv.fr",
            owner_name="CERT-FR / ANSSI",
            legal_basis="Public government security advisories — open access",
            contains_personal_data=False,
        ),
    )


# ── Per-file ingestion ─────────────────────────────────────────────────────────


async def _ingest_snapshot(
    entry: _SnapshotEntry,
    session_factory: async_sessionmaker[AsyncSession],
    source_repo: SourceSystemQueries,
    run_repo: IngestionRunQueries,
) -> dict[str, Any]:
    """Ingest a single TXT snapshot into the DB. Returns a report row."""
    text = entry.data.decode("utf-8", errors="replace").strip()
    title = _extract_title_from_text(text)
    label = _derive_label_from_text(text, title)
    url = f"https://www.cert.ssi.gouv.fr/cti/{entry.certfr_id}/"

    async with session_factory() as session:
        # Idempotency guard — same certfr_id + content_hash already ingested?
        result = await session.execute(
            select(DataRawObject).where(
                DataRawObject.external_ref == entry.certfr_id,
                DataRawObject.content_hash == entry.sha256,
            )
        )
        if result.scalar_one_or_none():
            logger.info("Already ingested: %s — skipping", entry.certfr_id)
            return {
                "certfr_id": entry.certfr_id,
                "source": entry.label,
                "inserted": 0,
                "status": "skipped_unchanged",
            }

        source_sys = await _get_or_create_source_system(session, source_repo)
        started_at = datetime.now(timezone.utc)

        ingestion_run = await run_repo.create(
            session,
            IngestionRunCreate(
                source_system_id=source_sys.id,
                trigger_mode="manual",
                status=IngestionStatus.PENDING,
                started_at=started_at,
            ),
        )

        raw_object = DataRawObject(
            ingestion_run_id=ingestion_run.id,
            external_ref=entry.certfr_id,
            object_type=ObjectType.API_PAYLOAD,
            storage_uri=entry.storage_uri,
            source_format="txt",
            content_hash=entry.sha256,
            size_bytes=entry.size_bytes,
            source_metadata={
                "filename": entry.filename,
                "certfr_id": entry.certfr_id,
                "title": title,
                "url": url,
            },
            collected_at=started_at,
        )
        session.add(raw_object)
        await session.flush()

        record_key = hashlib.sha256(
            text[:300].encode("utf-8", errors="ignore")
        ).hexdigest()

        raw_content = json.dumps(
            {
                "text": text,
                "label": label,
                "source": SOURCE_MACHINE_NAME,
                "certfr_id": entry.certfr_id,
                "title": title,
                "url": url,
                "language": "fr",
            },
            ensure_ascii=False,
            sort_keys=True,
        )

        raw_record = DataRawRecord(
            raw_object_id=raw_object.id,
            source_system_id=source_sys.id,
            record_key=record_key,
            raw_content=raw_content,
            detected_language="fr",
            is_usable=bool(text),
            rejection_reason=None if text else "empty_text",
            extracted_at=started_at,
        )
        session.add(raw_record)

        ingestion_run.finished_at = datetime.now(timezone.utc)
        ingestion_run.status = IngestionStatus.COMPLETED
        ingestion_run.raw_record_count = 1
        ingestion_run.raw_object_count = 1

        try:
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Commit failed for %s", entry.certfr_id)
            return {
                "certfr_id": entry.certfr_id,
                "source": entry.label,
                "inserted": 0,
                "status": "error",
            }

    return {
        "certfr_id": entry.certfr_id,
        "source": entry.label,
        "inserted": 1,
        "status": "ok",
        "label": label,
    }


# ── Report ─────────────────────────────────────────────────────────────────────


def _print_report(rows: list[dict[str, Any]], totals: dict[str, int]) -> None:
    sep = "=" * 76
    thin = "-" * 76
    print(f"\n{sep}")
    print("  CERT-FR BASE INGESTION — REPORT")
    print(sep)
    print(f"  {'CERTFR-ID':<30} {'SRC':<6} {'NEW':>4} {'LABEL':<12} {'STATUS'}")
    print(thin)
    for row in rows:
        print(
            f"  {row['certfr_id']:<30} {row['source'].upper():<6} "
            f"{row['inserted']:>4}  {row.get('label', '-'):<12} {row['status']}"
        )
    print(thin)
    print(f"  {'TOTAL':<38} {totals['inserted']:>4}")
    print(sep)
    total_cumulative = PRIOR_RECORD_COUNT + totals["inserted"]
    print(f"\n  Records before this run (after File) : {PRIOR_RECORD_COUNT:>7,}")
    print(f"  New records inserted this run         : {totals['inserted']:>7,}")
    print(f"  Cumulative total in sicurre.db        : {total_cumulative:>7,}")
    print(f"\n  Manifest → {MANIFEST_PATH.relative_to(ROOT_DIR)}")
    print(sep)


# ── Async DB insertion ─────────────────────────────────────────────────────────


async def _run_db_ingestion(
    entries: list[_SnapshotEntry],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Insert all snapshots into the DB. Returns (rows, totals)."""
    settings = get_settings()
    logger.info("Using database: %s", settings.database_url)
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    source_repo = SourceSystemQueries()
    run_repo = IngestionRunQueries()

    totals: dict[str, int] = {"inserted": 0}
    rows: list[dict[str, Any]] = []

    for entry in entries:
        row = await _ingest_snapshot(entry, session_factory, source_repo, run_repo)
        rows.append(row)
        totals["inserted"] += row["inserted"]
        logger.info(
            "  [%s] %s → inserted=%d status=%s",
            entry.label.upper(),
            entry.certfr_id,
            row["inserted"],
            row["status"],
        )

    await engine.dispose()
    return rows, totals


# ── Main ───────────────────────────────────────────────────────────────────────


def main() -> None:
    # All synchronous work (R2 download, manifest) is done before asyncio.run()
    # to avoid blocking the event loop with network I/O.

    # 1. Enumerate snapshots from R2 (sync)
    r2 = R2ReadClient()
    logger.info("Enumerating R2 snapshots under %s/ …", R2_CERTFR_PREFIX)
    entries = _enumerate_r2_snapshots(r2)
    logger.info("R2 snapshots found: %d", len(entries))

    # 2. Write manifest before any DB writes
    _save_manifest(entries)

    # 3. Run async DB ingestion
    rows, totals = asyncio.run(_run_db_ingestion(entries))

    # 4. Summary
    _print_report(rows, totals)


if __name__ == "__main__":
    main()
