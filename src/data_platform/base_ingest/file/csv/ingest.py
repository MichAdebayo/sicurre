"""Base ingestion for the File source — deterministic one-time population.

Handles all three file formats found under data/raw/file/:

  *.csv    →  delegated to ingest_csv_file() (csv_ingestion.py)
  *.jsonl  →  parsed by parse_jsonl()          (jsonl_ingestion.py)
  *.txt    →  parsed by parse_txt_emails()     (txt_email_ingestion.py)

Each format is enumerated in stable alphabetical order.  A single SHA-256
manifest is written to data/local/file_csv_base_ingest_manifest.json before
any DB writes, covering all three format groups.

Key properties:
- Local-only (no R2 for this source — files are static repo assets)
- No snapshot writes (files are already on disk; no SnapshotStore involved)
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
from core.trace_logger import SemanticTraceLogger  # noqa: E402
from db.models import DataRawObject, DataRawRecord  # noqa: E402
from db.queries import IngestionRunQueries, SourceSystemQueries  # noqa: E402
from data_platform.api.schemas import IngestionRunCreate  # noqa: E402
from data_platform.base_ingest.file.parsers.csv_ingestion import (  # noqa: E402
    get_or_create_source_system,
    ingest_csv_file,
)
from data_platform.base_ingest.file.parsers.jsonl_ingestion import parse_jsonl  # noqa: E402
from data_platform.base_ingest.file.parsers.txt_email_ingestion import (
    parse_txt_emails,
)  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

LOCAL_FILE_ROOT = ROOT_DIR / "data" / "raw" / "file"
LOCAL_CSV_DIR = LOCAL_FILE_ROOT / "csv"
LOCAL_TXT_DIR = LOCAL_FILE_ROOT / "txt"
MANIFEST_PATH = ROOT_DIR / "data" / "local" / "file_csv_base_ingest_manifest.json"

# JSONL file explicitly excluded per user decision (duplicate of fr CSV).
EXCLUDED_JSONL: frozenset[str] = frozenset({"data.jsonl"})

# Records in sicurre.db after PhishTank base ingestion — used only for delta.
PRIOR_RECORD_COUNT = 829


# ── Discovery ─────────────────────────────────────────────────────────────────


def _enumerate_csv_files() -> list[Path]:
    """Return all *.csv files under LOCAL_CSV_DIR, sorted for determinism."""
    if not LOCAL_CSV_DIR.exists():
        raise FileNotFoundError(f"CSV source directory not found: {LOCAL_CSV_DIR}")
    return sorted(
        LOCAL_CSV_DIR.rglob("*.csv"), key=lambda p: str(p.relative_to(LOCAL_CSV_DIR))
    )


def _enumerate_jsonl_files() -> list[Path]:
    """Return all *.jsonl files under LOCAL_CSV_DIR, excluding known out-of-scope names."""
    if not LOCAL_CSV_DIR.exists():
        return []
    return sorted(
        (p for p in LOCAL_CSV_DIR.rglob("*.jsonl") if p.name not in EXCLUDED_JSONL),
        key=lambda p: str(p.relative_to(LOCAL_CSV_DIR)),
    )


def _enumerate_txt_files() -> list[Path]:
    """Return all *.txt files under LOCAL_TXT_DIR, sorted for determinism."""
    if not LOCAL_TXT_DIR.exists():
        return []
    return sorted(
        LOCAL_TXT_DIR.rglob("*.txt"), key=lambda p: str(p.relative_to(LOCAL_TXT_DIR))
    )


# ── Manifest ──────────────────────────────────────────────────────────────────


def _build_and_save_manifest(all_files: list[Path]) -> list[dict[str, Any]]:
    """Compute SHA-256 for every file and persist the manifest.

    Written before any DB writes so replay information is always available even
    if the ingestion fails partway through.
    """
    records: list[dict[str, Any]] = []
    for path in all_files:
        data = path.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()
        try:
            rel = str(path.relative_to(ROOT_DIR))
        except ValueError:
            rel = str(path)
        records.append(
            {
                "filename": path.name,
                "relative_path": rel,
                "format": path.suffix.lstrip("."),
                "sha256": sha256,
                "size_bytes": path.stat().st_size,
            }
        )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": (
            "Exact local files used for the File-source base ingestion "
            "(CSV + JSONL + TXT). "
            "Replay with 'make file-ingest-base' on an empty DB to reproduce "
            "the identical dataset composition."
        ),
        "total_files": len(records),
        "files": records,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    logger.info("Manifest saved → %s", MANIFEST_PATH.relative_to(ROOT_DIR))
    return records


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


async def _persist_parsed_records(
    file_path: Path,
    parsed_records: list[Any],
    source_format: str,
    session_factory: Any,
    source_repo: SourceSystemQueries,
    run_repo: IngestionRunQueries,
    trigger_mode: str,
) -> dict[str, Any]:
    """Persist a list of parsed records (JsonlRecord or TxtEmailRecord) to the DB.

    Returns a row dict compatible with _print_report.
    """
    if not parsed_records:
        return {
            "filename": file_path.name,
            "fmt": source_format,
            "inserted": 0,
            "status": "empty",
        }

    file_stat = file_path.stat()
    file_content_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
    external_ref = f"local://{file_path.name}"

    async with session_factory() as session:
        # Idempotency guard — same file hash already ingested
        result = await session.execute(
            select(DataRawObject).where(
                DataRawObject.external_ref == external_ref,
                DataRawObject.content_hash == file_content_hash,
            )
        )
        if result.scalar_one_or_none():
            logger.info(
                "File %s already ingested (hash match). Skipping.", file_path.name
            )
            return {
                "filename": file_path.name,
                "fmt": source_format,
                "inserted": 0,
                "status": "skipped_unchanged",
            }

        # Source system — use record.source from the first record
        source_machine_name = parsed_records[0].source or file_path.stem.lower()
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
            external_ref=external_ref,
            object_type="api_payload",
            storage_uri=str(file_path.absolute()),
            source_format=source_format,
            content_hash=file_content_hash,
            size_bytes=file_stat.st_size,
            source_metadata={
                "filename": file_path.name,
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
            logger.exception("Commit failed for %s", file_path.name)
            return {
                "filename": file_path.name,
                "fmt": source_format,
                "inserted": 0,
                "status": "error",
            }

    logger.info("Inserted %d records for %s", len(records_to_add), file_path.name)
    return {
        "filename": file_path.name,
        "fmt": source_format,
        "inserted": len(records_to_add),
        "status": "ok",
    }


# ── Main ───────────────────────────────────────────────────────────────────────


async def run_base_ingestion() -> None:
    # 1. Discover all files
    csv_files = _enumerate_csv_files()
    jsonl_files = _enumerate_jsonl_files()
    txt_files = _enumerate_txt_files()

    logger.info(
        "Discovered: %d CSV, %d JSONL, %d TXT files",
        len(csv_files),
        len(jsonl_files),
        len(txt_files),
    )

    # 2. Save manifest (before DB writes)
    _build_and_save_manifest(csv_files + jsonl_files + txt_files)

    # 3. DB setup
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
    trace = SemanticTraceLogger(
        parent_type="File", child_target="File Base Ingest", domain="data_platform"
    )

    totals: dict[str, int] = {"inserted": 0}
    rows: list[dict[str, Any]] = []

    # 4a. CSV files — delegate to existing pipeline
    for csv_path in csv_files:
        logger.info("CSV: %s", csv_path.relative_to(ROOT_DIR))
        async with session_factory() as session:
            result = await ingest_csv_file(
                csv_path,
                session,
                source_repo,
                run_repo,
                trigger_mode="manual",
                trace=trace,
            )
        row: dict[str, Any] = {
            "filename": str(csv_path.relative_to(LOCAL_CSV_DIR)),
            "fmt": "csv",
            "inserted": result.inserted_count,
            "status": result.status,
        }
        rows.append(row)
        totals["inserted"] += result.inserted_count
        logger.info("  → inserted=%d  status=%s", result.inserted_count, result.status)

    # 4b. JSONL files
    for jsonl_path in jsonl_files:
        logger.info("JSONL: %s", jsonl_path.relative_to(ROOT_DIR))
        parsed = parse_jsonl(jsonl_path)
        row = await _persist_parsed_records(
            jsonl_path,
            parsed,
            "jsonl",
            session_factory,
            source_repo,
            run_repo,
            "manual",
        )
        rows.append(row)
        totals["inserted"] += row["inserted"]
        logger.info("  → inserted=%d  status=%s", row["inserted"], row["status"])

    # 4c. TXT email files
    for txt_path in txt_files:
        logger.info("TXT: %s", txt_path.relative_to(ROOT_DIR))
        parsed = parse_txt_emails(txt_path)
        row = await _persist_parsed_records(
            txt_path, parsed, "txt", session_factory, source_repo, run_repo, "manual"
        )
        rows.append(row)
        totals["inserted"] += row["inserted"]
        logger.info("  → inserted=%d  status=%s", row["inserted"], row["status"])

    await engine.dispose()

    # 5. Report
    _print_report(rows, totals)


if __name__ == "__main__":
    asyncio.run(run_base_ingestion())
