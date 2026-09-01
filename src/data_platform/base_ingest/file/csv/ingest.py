"""Base ingestion for the File source — deterministic one-time population.

Handles all three file formats found under raw-snapshots/base/file/ in R2:

  csv/  →  *.csv   delegated to ingest_csv_bytes() (csv_ingestion.py)
  csv/  →  *.jsonl parsed by parse_jsonl_from_bytes() (jsonl_ingestion.py)
  txt/  →  *.txt   parsed by parse_txt_emails_from_bytes() (txt_email_ingestion.py)

Each format is enumerated in stable alphabetical order (R2 key sort).
A single SHA-256 manifest is written to
data/local/file_csv_base_ingest_manifest.json before any DB writes.

Key properties:
- R2-first: reads exclusively from Cloudflare R2, no local data/raw/ files
- No snapshot writes (NoOpSnapshotStore not needed here — no SnapshotStore used)
- Idempotent: run twice → second run reports 0 new records for every file
- Must be run AFTER sicurre.db exists (alembic upgrade head or
  phishtank-ingest-base creates it)

data/raw/file/csv/french-spamham-detection-free/data.jsonl is excluded
per user decision — its 1,000 French spam/ham entries are already covered by
fr/french_spamham_1000_20260301.csv.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
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

from core.config import get_settings, redact_database_url  # noqa: E402
from core.database import Base  # noqa: E402
from core.trace_logger import SemanticTraceLogger  # noqa: E402
from db.models import DataRawObject, DataRawRecord  # noqa: E402
from db.queries import IngestionRunQueries, SourceSystemQueries  # noqa: E402
from data_platform.api.schemas import IngestionRunCreate  # noqa: E402
from data_platform.base_ingest.file.parsers.csv_ingestion import (  # noqa: E402
    get_or_create_source_system,
    ingest_csv_bytes,
)
from data_platform.base_ingest.file.parsers.jsonl_ingestion import (  # noqa: E402
    parse_jsonl_from_bytes,
)
from data_platform.base_ingest.file.parsers.txt_email_ingestion import (  # noqa: E402
    parse_txt_emails_from_bytes,
)
from data_platform.services.shared.r2_read_client import R2ReadClient  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

R2_CSV_PREFIX = "raw-snapshots/base/file/csv"
R2_TXT_PREFIX = "raw-snapshots/base/file/txt"
MANIFEST_DIR = ROOT_DIR / "data" / "local" / "base-manifest" / "file"
MANIFEST_PATH = MANIFEST_DIR / "file_csv_base_ingest_manifest.json"

# JSONL file explicitly excluded per user decision (duplicate of fr CSV).
EXCLUDED_JSONL: frozenset[str] = frozenset({"data.jsonl"})

# Records in sicurre.db after PhishTank base ingestion — used only for delta.
PRIOR_RECORD_COUNT = 829


@dataclass
class _R2FileEntry:
    r2_key: str
    r2_etag: str
    filename: str
    source_url: str
    data: bytes
    sha256: str
    size_bytes: int
    fmt: str  # "csv", "jsonl", or "txt"


def _enumerate_r2_files(r2: R2ReadClient) -> list[_R2FileEntry]:
    """Enumerate and download all CSV/JSONL/TXT files from R2 base prefixes.

    Returns entries sorted by R2 key for deterministic processing order.
    """
    entries: list[_R2FileEntry] = []

    # CSV and JSONL files live under the csv/ prefix
    for obj in r2.list_objects(R2_CSV_PREFIX):
        ext = (
            obj.key.rsplit(".", 1)[-1].lower()
            if "." in obj.key.rsplit("/", 1)[-1]
            else ""
        )
        if ext not in ("csv", "jsonl"):
            continue
        filename = obj.key.rsplit("/", 1)[-1]
        if ext == "jsonl" and filename in EXCLUDED_JSONL:
            logger.info("Skipping excluded JSONL: %s", filename)
            continue
        logger.info("Downloading R2: %s (%d bytes)", obj.key, obj.size_bytes)
        data = r2.download_bytes(obj.key)
        entries.append(
            _R2FileEntry(
                r2_key=obj.key,
                r2_etag=obj.etag,
                filename=filename,
                source_url=f"r2://{r2.bucket}/{obj.key}",
                data=data,
                sha256=hashlib.sha256(data).hexdigest(),
                size_bytes=len(data),
                fmt=ext,
            )
        )

    # TXT files live under the txt/ prefix
    for obj in r2.list_objects(R2_TXT_PREFIX):
        if not obj.key.lower().endswith(".txt"):
            continue
        filename = obj.key.rsplit("/", 1)[-1]
        logger.info("Downloading R2: %s (%d bytes)", obj.key, obj.size_bytes)
        data = r2.download_bytes(obj.key)
        entries.append(
            _R2FileEntry(
                r2_key=obj.key,
                r2_etag=obj.etag,
                filename=filename,
                source_url=f"r2://{r2.bucket}/{obj.key}",
                data=data,
                sha256=hashlib.sha256(data).hexdigest(),
                size_bytes=len(data),
                fmt="txt",
            )
        )

    return entries


# ── Manifest ──────────────────────────────────────────────────────────────────


def _build_and_save_manifest(entries: list[_R2FileEntry]) -> None:
    """Persist R2 provenance for every downloaded file.

    Written before any DB writes so replay information is always available even
    if the ingestion fails partway through.
    """
    records = [
        {
            "r2_key": e.r2_key,
            "r2_etag": e.r2_etag,
            "filename": e.filename,
            "source_url": e.source_url,
            "format": e.fmt,
            "sha256": e.sha256,
            "size_bytes": e.size_bytes,
        }
        for e in entries
    ]
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": (
            "R2-only File source base snapshots (CSV + JSONL + TXT). "
            "Replay with 'make file-ingest-base' on an empty DB to reproduce "
            "the identical dataset composition."
        ),
        "total_files": len(records),
        "files": records,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    logger.info("Manifest saved → %s", MANIFEST_PATH.relative_to(ROOT_DIR))


# ── Reporting ─────────────────────────────────────────────────────────────────


def _print_report(
    rows: list[dict[str, Any]],
    totals: dict[str, int],
) -> None:
    sep = "=" * 76
    thin = "-" * 76
    print(f"\n{sep}")
    print("  FILE SOURCE BASE INGESTION — REPORT")
    print(sep)
    print(f"  {'FILENAME':<52} {'FMT':>5} {'NEW':>7} {'STATUS'}")
    print(thin)
    for row in rows:
        print(
            f"  {row['filename']:<52} {row['fmt']:>5} {row['inserted']:>7}  {row['status']}"
        )
    print(thin)
    print(f"  {'TOTAL':<52} {'':>5} {totals['inserted']:>7}")
    print(sep)
    delta = totals["inserted"]
    total_cumulative = PRIOR_RECORD_COUNT + delta
    print(f"\n  Records before this run (after PhishTank) : {PRIOR_RECORD_COUNT:>7,}")
    print(f"  New records inserted this run             : {delta:>7,}")
    print(f"  Cumulative total in sicurre.db            : {total_cumulative:>7,}")
    print(f"\n  Manifest → {MANIFEST_PATH.relative_to(ROOT_DIR)}")
    print(sep)


# ── JSONL + TXT persistence (shared helper) ────────────────────────────────────


async def _persist_parsed_records_from_bytes(
    entry: _R2FileEntry,
    parsed_records: list[Any],
    session_factory: Any,
    source_repo: SourceSystemQueries,
    run_repo: IngestionRunQueries,
    trigger_mode: str,
) -> dict[str, Any]:
    """Persist a list of parsed records (JsonlRecord or TxtEmailRecord) to the DB.

    R2-first variant: file size and content hash come from the pre-downloaded
    _R2FileEntry instead of the filesystem.  Returns a row dict compatible
    with _print_report.
    """
    if not parsed_records:
        return {
            "filename": entry.filename,
            "fmt": entry.fmt,
            "inserted": 0,
            "status": "empty",
        }

    async with session_factory() as session:
        # Idempotency guard — same R2 source_url + hash already ingested
        result = await session.execute(
            select(DataRawObject).where(
                DataRawObject.external_ref == entry.source_url,
                DataRawObject.content_hash == entry.sha256,
            )
        )
        if result.scalar_one_or_none():
            logger.info(
                "File %s already ingested (hash match). Skipping.", entry.filename
            )
            return {
                "filename": entry.filename,
                "fmt": entry.fmt,
                "inserted": 0,
                "status": "skipped_unchanged",
            }

        # Source system — use record.source from the first parsed record
        source_machine_name = (
            parsed_records[0].source or entry.filename.rsplit(".", 1)[0].lower()
        )
        source_sys = await get_or_create_source_system(
            session, source_repo, source_machine_name
        )

        started_at = datetime.now(timezone.utc)
        ingestion_run = await run_repo.create(
            session,
            payload=IngestionRunCreate(
                source_system_id=source_sys.id,
                trigger_mode=trigger_mode,
                status="pending",
                started_at=started_at,
            ),
        )

        raw_object = DataRawObject(
            ingestion_run_id=ingestion_run.id,
            external_ref=entry.source_url,
            object_type="api_payload",
            storage_uri=entry.source_url,
            source_format=entry.fmt,
            content_hash=entry.sha256,
            size_bytes=entry.size_bytes,
            source_metadata={
                "filename": entry.filename,
                "r2_key": entry.r2_key,
                "entry_count": len(parsed_records),
            },
            collected_at=started_at,
        )
        session.add(raw_object)
        await session.flush()

        extracted_at = datetime.now(timezone.utc)
        records_to_add: list[DataRawRecord] = []
        raw_keys_seen: set[str] = set()

        for idx, rec in enumerate(parsed_records, start=1):
            text = rec.text.strip() if rec.text else ""
            record_key = (
                hashlib.sha256(text[:300].encode("utf-8", errors="ignore")).hexdigest()
                if text
                else f"empty-text-{idx}"
            )
            if record_key in raw_keys_seen:
                continue
            raw_keys_seen.add(record_key)

            is_usable = bool(text)
            raw_content = json.dumps(
                {
                    "text": text,
                    "label": rec.label,
                    "source": rec.source,
                    "language": rec.language,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            records_to_add.append(
                DataRawRecord(
                    raw_object_id=raw_object.id,
                    source_system_id=source_sys.id,
                    record_key=record_key,
                    raw_content=raw_content,
                    detected_language=rec.language,
                    is_usable=is_usable,
                    rejection_reason=None if is_usable else "empty_text",
                    extracted_at=extracted_at,
                )
            )

        chunk_size = 5_000
        for i in range(0, len(records_to_add), chunk_size):
            session.add_all(records_to_add[i : i + chunk_size])

        ingestion_run.finished_at = datetime.now(timezone.utc)
        ingestion_run.status = "completed"
        ingestion_run.raw_record_count = len(records_to_add)

        try:
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Commit failed for %s", entry.filename)
            return {
                "filename": entry.filename,
                "fmt": entry.fmt,
                "inserted": 0,
                "status": "error",
            }

    logger.info("Inserted %d records for %s", len(records_to_add), entry.filename)
    return {
        "filename": entry.filename,
        "fmt": entry.fmt,
        "inserted": len(records_to_add),
        "status": "ok",
    }


# ── Main ───────────────────────────────────────────────────────────────────────


async def run_base_ingestion() -> None:
    # 1. Enumerate + download all files from R2
    r2 = R2ReadClient()
    logger.info("Enumerating R2 file source objects...")
    entries = _enumerate_r2_files(r2)

    csv_entries = [e for e in entries if e.fmt == "csv"]
    jsonl_entries = [e for e in entries if e.fmt == "jsonl"]
    txt_entries = [e for e in entries if e.fmt == "txt"]

    logger.info(
        "Discovered: %d CSV, %d JSONL, %d TXT files",
        len(csv_entries),
        len(jsonl_entries),
        len(txt_entries),
    )

    # 2. Save manifest (before DB writes)
    _build_and_save_manifest(entries)

    # 3. DB setup
    settings = get_settings()
    logger.info("Using database: %s", redact_database_url(settings.data_platform_database_url))
    engine = create_async_engine(settings.data_platform_database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    source_repo = SourceSystemQueries()
    run_repo = IngestionRunQueries()
    trace = SemanticTraceLogger(
        parent_type="File", child_target="File Base Ingest", domain="data_platform"
    )

    totals: dict[str, int] = {"inserted": 0}
    rows: list[dict[str, Any]] = []

    # 4a. CSV files
    for entry in csv_entries:
        logger.info("CSV: %s", entry.r2_key)
        async with session_factory() as session:
            result = await ingest_csv_bytes(
                entry.data,
                entry.filename,
                entry.source_url,
                entry.source_url,
                session,
                source_repo,
                run_repo,
                trigger_mode="manual",
                trace=trace,
            )
        row: dict[str, Any] = {
            "filename": entry.filename,
            "fmt": "csv",
            "inserted": result.inserted_count,
            "status": result.status,
        }
        rows.append(row)
        totals["inserted"] += result.inserted_count
        logger.info("  → inserted=%d  status=%s", result.inserted_count, result.status)

    # 4b. JSONL files
    for entry in jsonl_entries:
        logger.info("JSONL: %s", entry.r2_key)
        source = entry.filename.rsplit(".", 1)[0].lower()
        parsed = parse_jsonl_from_bytes(entry.data, source)
        row = await _persist_parsed_records_from_bytes(
            entry, parsed, session_factory, source_repo, run_repo, "manual"
        )
        rows.append(row)
        totals["inserted"] += row["inserted"]
        logger.info("  → inserted=%d  status=%s", row["inserted"], row["status"])

    # 4c. TXT email files
    for entry in txt_entries:
        logger.info("TXT: %s", entry.r2_key)
        source = entry.filename.rsplit(".", 1)[0].lower()
        parsed = parse_txt_emails_from_bytes(entry.data, source)
        row = await _persist_parsed_records_from_bytes(
            entry, parsed, session_factory, source_repo, run_repo, "manual"
        )
        rows.append(row)
        totals["inserted"] += row["inserted"]
        logger.info("  → inserted=%d  status=%s", row["inserted"], row["status"])

    await engine.dispose()

    # 5. Report
    _print_report(rows, totals)


if __name__ == "__main__":
    asyncio.run(run_base_ingestion())
