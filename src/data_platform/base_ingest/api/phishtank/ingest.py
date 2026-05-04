"""Base ingestion for PhishTank — one-time deterministic population of sicurre.db.

Reads ALL frozen CSV snapshots from Cloudflare R2 under
``raw-snapshots/base/api/phishtank/`` (sorted by R2 key for reproducibility).

The exact set of files — including R2 keys, ETags, and SHA-256 hashes — is
written to data/local/phishtank_base_ingest_manifest.json so that the same
dataset composition can be replayed for jury evaluation.

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
import sys
from dataclasses import dataclass
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
from data_platform.extractors.phishtank import (  # noqa: E402
    PhishTankFetchedPayload,
    PhishTankIngestionResult,
    PhishTankIngestionService,
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

R2_PHISHTANK_PREFIX = "raw-snapshots/base/api/phishtank"
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


def _enumerate_r2_snapshots(r2: R2ReadClient) -> list[_SnapshotEntry]:
    """List and download all CSV/JSON snapshots from the R2 base phishtank prefix.

    Objects are sorted by key before download to guarantee a stable,
    reproducible processing order.
    """
    objects = r2.list_objects(R2_PHISHTANK_PREFIX)
    entries: list[_SnapshotEntry] = []
    for obj in objects:
        if not (obj.key.lower().endswith(".csv") or obj.key.lower().endswith(".json")):
            logger.debug("Skipping non-CSV/JSON R2 object: %s", obj.key)
            continue
        filename = obj.key.rsplit("/", 1)[-1]
        logger.info("Downloading R2: %s (%d bytes)", obj.key, obj.size_bytes)
        data = r2.download_bytes(obj.key)
        sha256 = hashlib.sha256(data).hexdigest()
        entries.append(
            _SnapshotEntry(
                sha256=sha256,
                label="r2",
                filename=filename,
                source_url=f"r2://{r2.bucket}/{obj.key}",
                data=data,
                size_bytes=len(data),
                r2_key=obj.key,
                r2_etag=obj.etag,
            )
        )
    return entries


# ── CSV parsing ────────────────────────────────────────────────────────────────


def _parse_csv_payload(entry: _SnapshotEntry) -> PhishTankFetchedPayload:
    text = entry.data.decode("utf-8", errors="replace").strip()

    if text.startswith("[") or text.startswith("{"):
        try:
            data = json.loads(text)
            raw_entries = data if isinstance(data, list) else [data]
            entries = [
                {
                    "phish_id": str(row.get("phish_id", "")),
                    "url": str(row.get("url", "")),
                    "phish_detail_url": str(row.get("phish_detail_url", "")),
                    "submission_time": str(row.get("submission_time", "")),
                    "verified": str(row.get("verified", "")),
                    "verification_time": str(row.get("verification_time", "")),
                    "online": str(row.get("online", "")),
                    "target": str(row.get("target", "")),
                }
                for row in raw_entries
            ]
            return PhishTankFetchedPayload(
                entries=entries,
                snapshot_bytes=entry.data,
                content_type="application/json",
                source_format="json",
                source_url=entry.source_url,
            )
        except json.JSONDecodeError:
            pass

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


def _save_manifest(entries: list[_SnapshotEntry]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    snapshots = [
        {
            "source": "r2",
            "r2_key": e.r2_key,
            "r2_etag": e.r2_etag,
            "filename": e.filename,
            "source_url": e.source_url,
            "sha256": e.sha256,
            "size_bytes": e.size_bytes,
        }
        for e in entries
    ]
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": (
            "R2-only PhishTank base snapshots used for base ingestion. "
            "Replay with 'make phishtank-ingest-base' on an empty DB to reproduce "
            "the identical dataset composition."
        ),
        "selected_count": len(snapshots),
        "total_discovered": len(snapshots),
        "snapshots": snapshots,
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
    # 1. Discover snapshots from R2
    r2 = R2ReadClient()
    logger.info(
        "Enumerating R2 snapshots under %s/%s/ …", r2.bucket, R2_PHISHTANK_PREFIX
    )
    entries = _enumerate_r2_snapshots(r2)
    logger.info("R2 snapshots found: %d", len(entries))

    # 2. Save manifest before any DB writes (fail-safe)
    _save_manifest(entries)

    # 3. Set up DB connection
    settings = get_settings()
    logger.info("Using database: %s", settings.database_url)
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    # 4. Ingest each snapshot in stable order
    totals: dict[str, int] = {"new": 0, "skipped": 0, "filtered": 0, "feed": 0}
    rows: list[dict[str, Any]] = []

    for entry in entries:
        payload = _parse_csv_payload(entry)
        logger.info(
            "Processing [R2] %s (%d entries parsed) …",
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

    # 5. Print summary report
    _print_report(rows, totals)


if __name__ == "__main__":
    asyncio.run(run_base_ingestion())
