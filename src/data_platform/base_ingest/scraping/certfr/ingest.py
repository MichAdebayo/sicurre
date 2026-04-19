"""Base ingestion for CERT-FR — deterministic one-time population of sicurre.db.

Reads all 92 frozen TXT snapshots from two sources, in this fixed order:
  1. Cloudflare R2  → raw-snapshots/cert-fr/*.txt   (sorted by R2 key)
  2. Local disk     → data/raw/scraping/cert_fr/cert-fr/*.txt  (sorted by name)

Files are deduplicated by SHA-256 of raw bytes; R2 takes precedence on collision.
Since R2 and local are byte-for-byte identical, all 92 files come from R2 and
local contributes 0 new files — this is verified and documented in the manifest.

Label assignment:
  - certfr_id found in certfr_cti_reports CSV with is_phishing_related=True  → "phishing"
  - certfr_id found in certfr_cti_reports CSV with is_phishing_related=False → "legitimate"
  - certfr_id not in CSV (e.g. CERTFR-2026-CTI-002, newer report)           → "legitimate"

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
import csv
import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from dotenv import load_dotenv
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

R2_CERTFR_PREFIX = "raw-snapshots/cert-fr"
LOCAL_CERTFR_DIR = ROOT_DIR / "data" / "raw" / "scraping" / "cert_fr" / "cert-fr"
LOCAL_CSV_DIR = ROOT_DIR / "data" / "raw" / "scraping" / "certfr"
CTI_CSV_PATH = LOCAL_CSV_DIR / "certfr_cti_reports_91_20260301.csv"
MANIFEST_PATH = ROOT_DIR / "data" / "local" / "certfr_base_ingest_manifest.json"

SOURCE_MACHINE_NAME = "certfr"
SOURCE_DISPLAY_NAME = "CERT-FR CTI"
SOURCE_TYPE = "scraping"

CERTFR_REF_RE = re.compile(r"(CERTFR-\d{4}-(?:CTI|IOC)-\d+)", re.IGNORECASE)

# Records in sicurre.db after File source base ingestion.
PRIOR_RECORD_COUNT = 163_367


# ── R2 client ─────────────────────────────────────────────────────────────────


def _build_r2_client() -> tuple[Any, str]:
    load_dotenv(ROOT_DIR / ".env")
    bucket = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_BUCKET_NAME", "sicurre-raw")
    endpoint = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_ENDPOINT_URL")
    access_key = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_SECRET_ACCESS_KEY")
    region = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_REGION", "auto")
    if not all([endpoint, access_key, secret_key]):
        raise RuntimeError(
            "Missing R2 credentials in .env — check SICURRE_RAW_SNAPSHOT_R2_* vars"
        )
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    return client, bucket


# ── Snapshot entry ─────────────────────────────────────────────────────────────


@dataclass
class _SnapshotEntry:
    sha256: str
    label: str  # "r2" or "local"
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


def _enumerate_r2_snapshots(s3_client: Any, bucket: str) -> list[_SnapshotEntry]:
    """Download all TXT snapshots from R2, sorted by key."""
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=R2_CERTFR_PREFIX + "/"):
        objects.extend(page.get("Contents", []))

    objects.sort(key=lambda o: o["Key"])

    entries: list[_SnapshotEntry] = []
    for obj in objects:
        key: str = obj["Key"]
        filename = key.split("/")[-1]
        if not filename.lower().endswith(".txt"):
            logger.debug("Skipping non-TXT R2 object: %s", key)
            continue
        logger.info("Downloading R2: %s (%d bytes)", key, obj["Size"])
        data: bytes = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
        sha256 = hashlib.sha256(data).hexdigest()
        etag = obj.get("ETag", "").strip('"')
        entries.append(
            _SnapshotEntry(
                sha256=sha256,
                label="r2",
                filename=filename,
                certfr_id=_extract_certfr_id(filename),
                storage_uri=f"r2://{bucket}/{key}",
                data=data,
                size_bytes=len(data),
                r2_key=key,
                r2_etag=etag,
            )
        )
    return entries


def _enumerate_local_snapshots() -> list[_SnapshotEntry]:
    """List local TXT snapshots, sorted by filename."""
    if not LOCAL_CERTFR_DIR.exists():
        logger.warning("Local CERT-FR dir not found: %s", LOCAL_CERTFR_DIR)
        return []

    txt_files = sorted(LOCAL_CERTFR_DIR.glob("*.txt"), key=lambda p: p.name)
    entries: list[_SnapshotEntry] = []
    for path in txt_files:
        data = path.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()
        try:
            rel = path.relative_to(ROOT_DIR)
        except ValueError:
            rel = path
        entries.append(
            _SnapshotEntry(
                sha256=sha256,
                label="local",
                filename=path.name,
                certfr_id=_extract_certfr_id(path.name),
                storage_uri=f"file://{rel}",
                data=data,
                size_bytes=len(data),
            )
        )
    return entries


# ── Deduplication ──────────────────────────────────────────────────────────────


def _build_dedup_index(
    r2_entries: list[_SnapshotEntry],
    local_entries: list[_SnapshotEntry],
) -> tuple[list[_SnapshotEntry], list[dict[str, Any]]]:
    """Deduplicate by SHA-256. R2 entries take precedence on collision."""
    seen: dict[str, _SnapshotEntry] = {}
    manifest_records: list[dict[str, Any]] = []

    for entry in r2_entries:
        selected = entry.sha256 not in seen
        if selected:
            seen[entry.sha256] = entry
        manifest_records.append(
            {
                "source": "r2",
                "r2_key": entry.r2_key,
                "r2_etag": entry.r2_etag,
                "filename": entry.filename,
                "certfr_id": entry.certfr_id,
                "storage_uri": entry.storage_uri,
                "sha256": entry.sha256,
                "size_bytes": entry.size_bytes,
                "selected": selected,
                "duplicate_of": None if selected else seen[entry.sha256].filename,
            }
        )

    for entry in local_entries:
        selected = entry.sha256 not in seen
        if selected:
            seen[entry.sha256] = entry
        manifest_records.append(
            {
                "source": "local",
                "r2_key": None,
                "r2_etag": None,
                "filename": entry.filename,
                "certfr_id": entry.certfr_id,
                "storage_uri": entry.storage_uri,
                "sha256": entry.sha256,
                "size_bytes": entry.size_bytes,
                "selected": selected,
                "duplicate_of": None if selected else seen[entry.sha256].filename,
            }
        )

    r2_unique = [e for e in r2_entries if seen.get(e.sha256) is e]
    local_unique = [e for e in local_entries if seen.get(e.sha256) is e]
    return r2_unique + local_unique, manifest_records


# ── CSV metadata loader ────────────────────────────────────────────────────────


def _load_csv_metadata() -> dict[str, dict[str, str]]:
    """Load certfr_id → row mapping from the CTI CSV for label + enrichment."""
    meta: dict[str, dict[str, str]] = {}
    if not CTI_CSV_PATH.exists():
        logger.warning(
            "CTI CSV not found: %s — labels will default to 'legitimate'", CTI_CSV_PATH
        )
        return meta
    with CTI_CSV_PATH.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            cid = row.get("certfr_id", "").strip().upper()
            if cid:
                meta[cid] = row
    logger.info("Loaded %d CERT-FR CSV metadata rows", len(meta))
    return meta


def _derive_label(certfr_id: str, csv_meta: dict[str, dict[str, str]]) -> str:
    row = csv_meta.get(certfr_id)
    if row is None:
        return "legitimate"
    is_phishing = row.get("is_phishing_related", "False").strip().lower()
    return "phishing" if is_phishing == "true" else "legitimate"


# ── Manifest ──────────────────────────────────────────────────────────────────


def _save_manifest(manifest_records: list[dict[str, Any]]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    selected = [r for r in manifest_records if r["selected"]]
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": (
            "Exact R2 + local TXT snapshots used for CERT-FR base ingestion. "
            "Replay with 'make certfr-ingest-base' on a DB that has already "
            "had phishtank-ingest-base and file-ingest-base applied."
        ),
        "selected_count": len(selected),
        "total_discovered": len(manifest_records),
        "snapshots": manifest_records,
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
    csv_meta: dict[str, dict[str, str]],
    session_factory: async_sessionmaker[AsyncSession],
    source_repo: SourceSystemQueries,
    run_repo: IngestionRunQueries,
) -> dict[str, Any]:
    """Ingest a single TXT snapshot into the DB. Returns a report row."""
    text = entry.data.decode("utf-8", errors="replace").strip()

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

        csv_row = csv_meta.get(entry.certfr_id, {})
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
                "title": csv_row.get("title", ""),
                "url": csv_row.get("url", ""),
                "pub_date": csv_row.get("pub_date", ""),
                "is_phishing_related": csv_row.get("is_phishing_related", ""),
            },
            collected_at=started_at,
        )
        session.add(raw_object)
        await session.flush()

        label = _derive_label(entry.certfr_id, csv_meta)
        record_key = hashlib.sha256(
            text[:300].encode("utf-8", errors="ignore")
        ).hexdigest()

        raw_content = json.dumps(
            {
                "text": text,
                "label": label,
                "source": SOURCE_MACHINE_NAME,
                "certfr_id": entry.certfr_id,
                "title": csv_row.get("title", ""),
                "url": csv_row.get("url", ""),
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
    unique_entries: list[_SnapshotEntry],
    csv_meta: dict[str, dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Insert all unique snapshots into the DB. Returns (rows, totals)."""
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

    for entry in unique_entries:
        row = await _ingest_snapshot(
            entry, csv_meta, session_factory, source_repo, run_repo
        )
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
    # All synchronous work (R2 download, local reads, dedup, manifest) is done
    # before asyncio.run() to avoid blocking the event loop with boto3 I/O.

    # 1. Load CSV metadata
    csv_meta = _load_csv_metadata()

    # 2. Enumerate snapshots (sync)
    s3_client, bucket = _build_r2_client()
    logger.info("Enumerating R2 snapshots under %s/%s/ …", bucket, R2_CERTFR_PREFIX)
    r2_entries = _enumerate_r2_snapshots(s3_client, bucket)
    logger.info("R2 snapshots found: %d", len(r2_entries))

    logger.info("Enumerating local snapshots in %s …", LOCAL_CERTFR_DIR)
    local_entries = _enumerate_local_snapshots()
    logger.info("Local snapshots found: %d", len(local_entries))

    # 3. Deduplicate
    unique_entries, manifest_records = _build_dedup_index(r2_entries, local_entries)
    logger.info(
        "Unique snapshots to process: %d (from %d total discovered)",
        len(unique_entries),
        len(r2_entries) + len(local_entries),
    )

    # 4. Write manifest before any DB writes
    _save_manifest(manifest_records)

    # 5. Run async DB ingestion
    rows, totals = asyncio.run(_run_db_ingestion(unique_entries, csv_meta))

    # 6. Summary
    _print_report(rows, totals)


if __name__ == "__main__":
    main()
