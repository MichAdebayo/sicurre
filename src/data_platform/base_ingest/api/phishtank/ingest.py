"""Base ingestion for PhishTank — one-time deterministic population of sicurre.db.

Reads ALL frozen CSV snapshots from two sources, in this fixed order:
  1. Cloudflare R2  → raw-snapshots/phishtank/*.csv  (sorted by R2 key)
  2. Local disk     → data/raw/api/phishtank/*.csv    (sorted by filename)

Files are deduplicated by SHA-256 of raw bytes so any file present in both R2
and local is only processed once (R2 copy takes precedence).

After discovery the exact set of files — including R2 keys, ETags, and SHA-256
hashes — is written to data/local/phishtank_base_ingest_manifest.json so that
the exact same dataset composition can be replayed for jury evaluation.

This script is read-only with respect to snapshot storage: it uses a
NoOpSnapshotStore that returns a stub SnapshotWriteResult without touching
disk or R2.  The sicurre.db reset and Alembic migration are handled by the
Makefile target (phishtank-ingest-base) before this script is called.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[5]  # repo root
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.config import get_settings  # noqa: E402
from core.database import Base  # noqa: E402
from data_platform.extractors.phishtank import (  # noqa: E402
    PhishTankFetchedPayload,
    PhishTankIngestionResult,
    PhishTankIngestionService,
)
from data_platform.services.shared.snapshot_storage import (
    SnapshotWriteResult,
)  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

R2_PHISHTANK_PREFIX = "raw-snapshots/phishtank"
LOCAL_PHISHTANK_DIR = ROOT_DIR / "data" / "raw" / "api" / "phishtank"
MANIFEST_PATH = ROOT_DIR / "data" / "local" / "phishtank_base_ingest_manifest.json"

# Records present in sicurre.db before this ingestion run (prior live-API run).
# Used only for the delta report — does not affect processing logic.
PRIOR_RECORD_COUNT = 679


# ── NoOpSnapshotStore ──────────────────────────────────────────────────────────


class NoOpSnapshotStore:
    """Satisfies the SnapshotStore protocol without writing to disk or R2.

    Returns a stub SnapshotWriteResult whose content_hash is computed from the
    payload so that DataRawObject.content_hash is still meaningful.
    """

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
            storage_uri=f"noop://phishtank/{object_key}",
            content_hash=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
            local_path=None,
        )


# ── Snapshot discovery ─────────────────────────────────────────────────────────


@dataclass
class _SnapshotEntry:
    sha256: str
    label: str  # "r2" or "local"
    filename: str
    source_url: str  # used as DataRawObject.external_ref
    data: bytes
    size_bytes: int
    r2_key: str | None = None
    r2_etag: str | None = None


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


def _enumerate_r2_snapshots(s3_client: Any, bucket: str) -> list[_SnapshotEntry]:
    """List and download all CSV snapshots from the R2 phishtank prefix.

    Objects are enumerated via paginator and sorted by key before download to
    guarantee a stable, reproducible processing order.
    """
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=R2_PHISHTANK_PREFIX + "/"):
        objects.extend(page.get("Contents", []))

    # Deterministic order: alphabetical by R2 key
    objects.sort(key=lambda o: o["Key"])

    entries: list[_SnapshotEntry] = []
    for obj in objects:
        key: str = obj["Key"]
        if not key.lower().endswith(".csv"):
            logger.debug("Skipping non-CSV R2 object: %s", key)
            continue
        filename = key.split("/")[-1]
        logger.info("Downloading R2: %s (%d bytes)", key, obj["Size"])
        data: bytes = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
        sha256 = hashlib.sha256(data).hexdigest()
        etag = obj.get("ETag", "").strip('"')
        entries.append(
            _SnapshotEntry(
                sha256=sha256,
                label="r2",
                filename=filename,
                source_url=f"r2://{bucket}/{key}",
                data=data,
                size_bytes=len(data),
                r2_key=key,
                r2_etag=etag,
            )
        )
    return entries


def _enumerate_local_snapshots() -> list[_SnapshotEntry]:
    """List all local CSV snapshots, sorted by filename for determinism."""
    if not LOCAL_PHISHTANK_DIR.exists():
        logger.warning("Local phishtank dir not found: %s", LOCAL_PHISHTANK_DIR)
        return []

    csv_files = sorted(LOCAL_PHISHTANK_DIR.glob("*.csv"), key=lambda p: p.name)
    entries: list[_SnapshotEntry] = []
    for path in csv_files:
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
                source_url=f"file://{rel}",
                data=data,
                size_bytes=len(data),
            )
        )
    return entries


def _build_dedup_index(
    r2_entries: list[_SnapshotEntry],
    local_entries: list[_SnapshotEntry],
) -> tuple[list[_SnapshotEntry], list[dict[str, Any]]]:
    """Deduplicate by SHA-256. R2 entries take precedence on collision.

    Returns:
        unique_entries: ordered list of snapshots to process (R2 first, then
            local-only), in stable alphabetical order within each group.
        manifest_records: full provenance record for every discovered file.
    """
    seen: dict[str, _SnapshotEntry] = {}  # sha256 -> first selected entry
    manifest_records: list[dict[str, Any]] = []

    # R2 first
    for entry in r2_entries:
        if entry.sha256 in seen:
            selected = False
            duplicate_of: str | None = seen[entry.sha256].filename
            logger.info(
                "Dedup: R2 '%s' is a duplicate of '%s' (sha256=%s…) — skipping",
                entry.filename,
                duplicate_of,
                entry.sha256[:12],
            )
        else:
            seen[entry.sha256] = entry
            selected = True
            duplicate_of = None

        manifest_records.append(
            {
                "source": "r2",
                "r2_key": entry.r2_key,
                "r2_etag": entry.r2_etag,
                "filename": entry.filename,
                "source_url": entry.source_url,
                "sha256": entry.sha256,
                "size_bytes": entry.size_bytes,
                "selected": selected,
                "duplicate_of": duplicate_of,
            }
        )

    # Local second (only add if hash not already seen from R2)
    for entry in local_entries:
        if entry.sha256 in seen:
            selected = False
            duplicate_of = seen[entry.sha256].filename
            logger.info(
                "Dedup: local '%s' matches existing '%s' (sha256=%s…) — skipping",
                entry.filename,
                duplicate_of,
                entry.sha256[:12],
            )
        else:
            seen[entry.sha256] = entry
            selected = True
            duplicate_of = None

        manifest_records.append(
            {
                "source": "local",
                "r2_key": None,
                "r2_etag": None,
                "filename": entry.filename,
                "source_url": entry.source_url,
                "sha256": entry.sha256,
                "size_bytes": entry.size_bytes,
                "selected": selected,
                "duplicate_of": duplicate_of,
            }
        )

    # Stable output order: selected R2 entries first (already sorted by key),
    # then selected local-only entries (already sorted by filename).
    r2_unique = [e for e in r2_entries if seen.get(e.sha256) is e]
    local_unique = [e for e in local_entries if seen.get(e.sha256) is e]
    unique_entries = r2_unique + local_unique

    return unique_entries, manifest_records


# ── CSV parsing ────────────────────────────────────────────────────────────────


def _parse_csv_payload(entry: _SnapshotEntry) -> PhishTankFetchedPayload:
    text = entry.data.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    entries = [
        {
            "phish_id": row.get("phish_id", ""),
            "url": row.get("url", ""),
            "phish_detail_url": row.get("phish_detail_url", ""),
            "submission_time": row.get("submission_time", ""),
            "verified": row.get("verified", ""),
            "verification_time": row.get("verification_time", ""),
            "online": row.get("online", ""),
            "target": row.get("target", ""),
        }
        for row in reader
    ]
    return PhishTankFetchedPayload(
        entries=entries,
        snapshot_bytes=entry.data,
        content_type="text/csv",
        source_format="csv",
        source_url=entry.source_url,
    )


# ── Manifest persistence ───────────────────────────────────────────────────────


def _save_manifest(manifest_records: list[dict[str, Any]]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    selected = [r for r in manifest_records if r["selected"]]
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": (
            "Exact R2 + local snapshots used for PhishTank base ingestion. "
            "Replay with 'make phishtank-ingest-base' on an empty DB to reproduce "
            "the identical dataset composition."
        ),
        "selected_count": len(selected),
        "total_discovered": len(manifest_records),
        "snapshots": manifest_records,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    logger.info("Manifest saved → %s", MANIFEST_PATH.relative_to(ROOT_DIR))


# ── Reporting ──────────────────────────────────────────────────────────────────


def _print_report(
    rows: list[dict[str, Any]],
    totals: dict[str, int],
) -> None:
    sep = "=" * 76
    thin = "-" * 76
    print(f"\n{sep}")
    print("  PHISHTANK BASE INGESTION — REPORT")
    print(sep)
    print(
        f"  {'SRC':<5} {'FILENAME':<48} {'NEW':>5} {'SKIP':>5} {'FILT':>5} {'FEED':>6}"
    )
    print(thin)
    for row in rows:
        print(
            f"  {row['label'].upper():<5} {row['filename']:<48} "
            f"{row['new']:>5} {row['skipped']:>5} {row['filtered']:>5} {row['feed']:>6}"
        )
    print(thin)
    print(
        f"  {'TOTAL':<54} {totals['new']:>5} {totals['skipped']:>5} "
        f"{totals['filtered']:>5} {totals['feed']:>6}"
    )
    print(sep)
    delta = totals["new"] - PRIOR_RECORD_COUNT
    sign = "+" if delta >= 0 else ""
    print(f"\n  Baseline (prior live run) : {PRIOR_RECORD_COUNT:>7,} records")
    print(f"  New records this run      : {totals['new']:>7,} records")
    print(f"  Delta vs baseline         : {sign}{delta:,}")
    print(f"\n  Manifest → {MANIFEST_PATH.relative_to(ROOT_DIR)}")
    print(sep)


# ── Main ───────────────────────────────────────────────────────────────────────


async def run_base_ingestion() -> None:
    # 1. Discover snapshots
    s3_client, bucket = _build_r2_client()
    logger.info("Enumerating R2 snapshots under %s/%s/ …", bucket, R2_PHISHTANK_PREFIX)
    r2_entries = _enumerate_r2_snapshots(s3_client, bucket)
    logger.info("R2 snapshots found: %d", len(r2_entries))

    logger.info("Enumerating local snapshots in %s …", LOCAL_PHISHTANK_DIR)
    local_entries = _enumerate_local_snapshots()
    logger.info("Local snapshots found: %d", len(local_entries))

    # 2. Deduplicate
    unique_entries, manifest_records = _build_dedup_index(r2_entries, local_entries)
    logger.info(
        "Unique snapshots to process: %d (from %d total discovered)",
        len(unique_entries),
        len(r2_entries) + len(local_entries),
    )

    # 3. Save manifest before any DB writes (fail-safe: manifest is always written)
    _save_manifest(manifest_records)

    # 4. Set up DB connection
    settings = get_settings()
    logger.info("Using database: %s", settings.database_url)
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    # 5. Ingest each unique snapshot in stable order
    totals: dict[str, int] = {"new": 0, "skipped": 0, "filtered": 0, "feed": 0}
    rows: list[dict[str, Any]] = []

    for entry in unique_entries:
        payload = _parse_csv_payload(entry)
        logger.info(
            "Processing [%s] %s (%d entries parsed) …",
            entry.label.upper(),
            entry.filename,
            len(payload.entries),
        )

        # Capture in closure to avoid late-binding issue in async loop
        async def _fetch(
            p: PhishTankFetchedPayload = payload,
        ) -> PhishTankFetchedPayload:
            return p

        service = PhishTankIngestionService(
            fetch_entries=_fetch,
            snapshot_store=NoOpSnapshotStore(),
        )

        async with session_factory() as session:
            result: PhishTankIngestionResult = await service.run(
                session, trigger_mode="manual"
            )

        row: dict[str, Any] = {
            "label": entry.label,
            "filename": entry.filename,
            "new": result.raw_record_count,
            "skipped": result.skipped_count,
            "filtered": result.filtered_count,
            "feed": result.total_feed_count,
        }
        rows.append(row)
        totals["new"] += result.raw_record_count
        totals["skipped"] += result.skipped_count
        totals["filtered"] += result.filtered_count
        totals["feed"] += result.total_feed_count

        logger.info(
            "  → new=%d  skipped=%d  filtered=%d  feed=%d",
            result.raw_record_count,
            result.skipped_count,
            result.filtered_count,
            result.total_feed_count,
        )

    await engine.dispose()

    # 6. Print summary report
    _print_report(rows, totals)


if __name__ == "__main__":
    asyncio.run(run_base_ingestion())
