"""Seed the current_frozen provenance into data_dataset + data_dataset_item.

Reads data/final/provenance/current_frozen/sicurre_{train,val,test}.csv,
matches each row to data_normalized_message by sha256(text), and inserts:
  - 1 data_dataset row (version_tag from metadata.json)
  - N data_dataset_item rows (one per matched normalized message)

Usage:
    uv run python scripts/data_platform/seed_frozen_dataset.py
    uv run python scripts/data_platform/seed_frozen_dataset.py --skip-if-exists
    uv run python scripts/data_platform/seed_frozen_dataset.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import csv
from dataclasses import dataclass
import hashlib
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

FROZEN_DIR = ROOT_DIR / "data" / "final" / "provenance" / "current_frozen"
SPLITS = ("train", "val", "test")
PROVENANCE_SLICE_DIRS = {
    "generated_pipeline": ROOT_DIR
    / "data"
    / "final"
    / "provenance"
    / "generated_pipeline_only",
    "adapted_db": ROOT_DIR / "data" / "final" / "provenance" / "adapted_db_only",
    "synthetic_db": ROOT_DIR / "data" / "final" / "provenance" / "synthetic_db_only",
    "native_external": ROOT_DIR
    / "data"
    / "final"
    / "provenance"
    / "native_external_only",
}


@dataclass(frozen=True)
class FrozenRow:
    text: str
    text_sha256: str
    split_name: str
    label: str


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_frozen_rows(frozen_dir: Path) -> list[FrozenRow]:
    """Return list of frozen rows from all split CSVs."""
    rows: list[FrozenRow] = []
    for split in SPLITS:
        csv_path = frozen_dir / f"sicurre_{split}.csv"
        if not csv_path.exists():
            logger.warning("Frozen CSV not found: %s — skipping split", csv_path)
            continue
        with csv_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                text_val = row.get("text", "")
                label = row.get("label", "")
                if text_val:
                    rows.append(
                        FrozenRow(
                            text=text_val,
                            text_sha256=_sha256_hex(text_val),
                            split_name=split,
                            label=label,
                        )
                    )
    return rows


def _load_provenance_hashes() -> dict[str, set[str]]:
    provenance_hashes: dict[str, set[str]] = {}
    for group_name, folder in PROVENANCE_SLICE_DIRS.items():
        hashes: set[str] = set()
        if not folder.exists():
            provenance_hashes[group_name] = hashes
            continue
        for row in _load_frozen_rows(folder):
            hashes.add(row.text_sha256)
        provenance_hashes[group_name] = hashes
    return provenance_hashes


def _estimate_provenance_group(
    text_sha256: str, provenance_hashes: dict[str, set[str]]
) -> str:
    for group_name in (
        "generated_pipeline",
        "adapted_db",
        "synthetic_db",
        "native_external",
    ):
        if text_sha256 in provenance_hashes.get(group_name, set()):
            return group_name
    return "unknown"


async def _load_normalized_matches(
    session: AsyncSession,
    sha256_values: list[str],
) -> dict[str, uuid.UUID | str]:
    matched: dict[str, uuid.UUID | str] = {}
    chunk_size = 900
    for i in range(0, len(sha256_values), chunk_size):
        chunk = sha256_values[i : i + chunk_size]
        placeholders = ", ".join(f":s{j}" for j in range(len(chunk)))
        params = {f"s{j}": sha for j, sha in enumerate(chunk)}
        stmt = text(
            f"SELECT id, text_sha256 FROM data_normalized_message "
            f"WHERE text_sha256 IN ({placeholders})"
        ).bindparams(**params)
        result = await session.execute(stmt)
        for row in result.fetchall():
            matched[row.text_sha256] = row.id
    return matched


async def _get_or_create_source_system(
    session: AsyncSession,
    *,
    source_name: str,
    description: str,
    now: datetime,
    to_uuid: callable,
    to_datetime: callable,
) -> uuid.UUID | str:
    existing = await session.scalar(
        text("SELECT id FROM data_source_system WHERE name = :name").bindparams(
            name=source_name
        )
    )
    if existing:
        return existing

    source_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO data_source_system "
            "(id, name, source_type, description, owner_name, legal_basis, contains_personal_data, is_active, created_at) "
            "VALUES (:id, :name, :source_type, :description, :owner_name, :legal_basis, :contains_personal_data, :is_active, :created_at)"
        ).bindparams(
            id=to_uuid(source_id),
            name=source_name,
            source_type="manual",
            description=description,
            owner_name="seed_frozen_dataset",
            legal_basis="reconstructed_frozen_dataset",
            contains_personal_data=False,
            is_active=True,
            created_at=to_datetime(now),
        )
    )
    return to_uuid(source_id)


async def _materialize_missing_rows(
    session: AsyncSession,
    *,
    missing_rows: list[FrozenRow],
    version_tag: str,
    estimated_source_prefix: str,
    provenance_hashes: dict[str, set[str]],
    now: datetime,
    to_uuid: callable,
    to_datetime: callable,
) -> None:
    if not missing_rows:
        return

    missing_by_group: dict[str, list[FrozenRow]] = {}
    for row in missing_rows:
        group_name = _estimate_provenance_group(row.text_sha256, provenance_hashes)
        missing_by_group.setdefault(group_name, []).append(row)

    logger.info(
        "Materializing %d missing frozen rows with estimated lineage: %s",
        len(missing_rows),
        dict(sorted((group, len(rows)) for group, rows in missing_by_group.items())),
    )

    processing_run_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO data_processing_run "
            "(id, pipeline_version, started_at, finished_at, status, normalized_count, rejected_count, report_uri, created_at) "
            "VALUES (:id, :pipeline_version, :started_at, :finished_at, :status, :normalized_count, :rejected_count, :report_uri, :created_at)"
        ).bindparams(
            id=to_uuid(processing_run_id),
            pipeline_version="current_frozen_reconstruction/v1",
            started_at=to_datetime(now),
            finished_at=to_datetime(now),
            status="completed",
            normalized_count=len(missing_rows),
            rejected_count=0,
            report_uri=f"reconstructed://current_frozen/{version_tag}/processing_run",
            created_at=to_datetime(now),
        )
    )

    raw_insert_stmt = text(
        "INSERT INTO data_raw_record "
        "(id, raw_object_id, source_system_id, record_key, raw_content, detected_language, is_usable, extracted_at, created_at) "
        "VALUES (:id, :raw_object_id, :source_system_id, :record_key, :raw_content, :detected_language, :is_usable, :extracted_at, :created_at)"
    )
    normalized_insert_stmt = text(
        "INSERT INTO data_normalized_message "
        "(id, raw_record_id, processing_run_id, normalized_text, text_sha256, language, current_label, quality_score, contains_pii, redaction_status, text_length, normalized_at, created_at) "
        "VALUES (:id, :raw_record_id, :processing_run_id, :normalized_text, :text_sha256, :language, :current_label, :quality_score, :contains_pii, :redaction_status, :text_length, :normalized_at, :created_at)"
    )
    annotation_insert_stmt = text(
        "INSERT INTO data_annotation "
        "(id, normalized_message_id, label, label_source, confidence, comment, is_validated, annotated_at, created_at) "
        "VALUES (:id, :normalized_message_id, :label, :label_source, :confidence, :comment, :is_validated, :annotated_at, :created_at)"
    )

    insert_batch_size = 500

    for group_name, grouped_rows in missing_by_group.items():
        source_name = f"{estimated_source_prefix}/{group_name}"
        source_id = await _get_or_create_source_system(
            session,
            source_name=source_name,
            description=(
                "Estimated lineage reconstructed from current_frozen provenance membership; "
                "original raw lineage unavailable."
            ),
            now=now,
            to_uuid=to_uuid,
            to_datetime=to_datetime,
        )

        ingestion_run_id = uuid.uuid4()
        raw_object_id = uuid.uuid4()
        object_hash = _sha256_hex(
            f"{version_tag}:{group_name}:current_frozen_reconstruction"
        )

        await session.execute(
            text(
                "INSERT INTO data_ingestion_run "
                "(id, source_system_id, started_at, finished_at, status, trigger_mode, raw_object_count, raw_record_count, log_message, created_at) "
                "VALUES (:id, :source_system_id, :started_at, :finished_at, :status, :trigger_mode, :raw_object_count, :raw_record_count, :log_message, :created_at)"
            ).bindparams(
                id=to_uuid(ingestion_run_id),
                source_system_id=source_id,
                started_at=to_datetime(now),
                finished_at=to_datetime(now),
                status="completed",
                trigger_mode="reconstructed_frozen_dataset",
                raw_object_count=1,
                raw_record_count=len(grouped_rows),
                log_message=(
                    f"Materialized missing frozen rows for version {version_tag} "
                    f"with estimated provenance group {group_name}."
                ),
                created_at=to_datetime(now),
            )
        )
        await session.execute(
            text(
                "INSERT INTO data_raw_object "
                "(id, ingestion_run_id, external_ref, object_type, storage_uri, source_format, content_hash, size_bytes, collected_at, created_at) "
                "VALUES (:id, :ingestion_run_id, :external_ref, :object_type, :storage_uri, :source_format, :content_hash, :size_bytes, :collected_at, :created_at)"
            ).bindparams(
                id=to_uuid(raw_object_id),
                ingestion_run_id=to_uuid(ingestion_run_id),
                external_ref=f"{version_tag}:{group_name}:missing_frozen_rows",
                object_type="file",
                storage_uri=f"reconstructed://current_frozen/{version_tag}/{group_name}",
                source_format="csv",
                content_hash=object_hash,
                size_bytes=None,
                collected_at=to_datetime(now),
                created_at=to_datetime(now),
            )
        )

        raw_rows = []
        normalized_rows = []
        annotation_rows = []
        for row in grouped_rows:
            raw_record_id = uuid.uuid4()
            normalized_message_id = uuid.uuid4()
            raw_rows.append(
                {
                    "id": to_uuid(raw_record_id),
                    "raw_object_id": to_uuid(raw_object_id),
                    "source_system_id": source_id,
                    "record_key": row.text_sha256,
                    "raw_content": json.dumps(
                        {
                            "text": row.text,
                            "label": row.label,
                            "frozen_version_tag": version_tag,
                            "estimated_provenance_group": group_name,
                            "lineage_mode": "estimated_from_provenance_export_membership",
                        },
                        ensure_ascii=False,
                    ),
                    "detected_language": "fr",
                    "is_usable": True,
                    "extracted_at": to_datetime(now),
                    "created_at": to_datetime(now),
                }
            )
            normalized_rows.append(
                {
                    "id": to_uuid(normalized_message_id),
                    "raw_record_id": to_uuid(raw_record_id),
                    "processing_run_id": to_uuid(processing_run_id),
                    "normalized_text": row.text,
                    "text_sha256": row.text_sha256,
                    "language": "fr",
                    "current_label": row.label,
                    "quality_score": None,
                    "contains_pii": False,
                    "redaction_status": "not_required",
                    "text_length": len(row.text),
                    "normalized_at": to_datetime(now),
                    "created_at": to_datetime(now),
                }
            )
            annotation_rows.append(
                {
                    "id": to_uuid(uuid.uuid4()),
                    "normalized_message_id": to_uuid(normalized_message_id),
                    "label": row.label,
                    "label_source": "manual_review",
                    "confidence": 1.0,
                    "comment": (
                        "Reconstructed from current_frozen export; provenance estimated from export membership."
                    ),
                    "is_validated": True,
                    "annotated_at": to_datetime(now),
                    "created_at": to_datetime(now),
                }
            )

        for i in range(0, len(raw_rows), insert_batch_size):
            batch = raw_rows[i : i + insert_batch_size]
            await session.execute(raw_insert_stmt, batch)
        for i in range(0, len(normalized_rows), insert_batch_size):
            batch = normalized_rows[i : i + insert_batch_size]
            await session.execute(normalized_insert_stmt, batch)
        for i in range(0, len(annotation_rows), insert_batch_size):
            batch = annotation_rows[i : i + insert_batch_size]
            await session.execute(annotation_insert_stmt, batch)

    await session.commit()


async def _load_existing_dataset_hashes(
    session: AsyncSession,
    dataset_id: uuid.UUID | str,
) -> set[str]:
    result = await session.execute(
        text(
            "SELECT nm.text_sha256 "
            "FROM data_dataset_item di "
            "JOIN data_normalized_message nm ON nm.id = di.normalized_message_id "
            "WHERE di.dataset_id = :dataset_id"
        ).bindparams(dataset_id=dataset_id)
    )
    return {row.text_sha256 for row in result.fetchall()}


async def _verify_dataset_sha_parity(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID | str,
    frozen_rows: list[FrozenRow],
) -> None:
    frozen_hashes = {row.text_sha256 for row in frozen_rows}
    dataset_hashes = await _load_existing_dataset_hashes(session, dataset_id)
    missing_hashes = frozen_hashes - dataset_hashes
    extra_hashes = dataset_hashes - frozen_hashes
    if missing_hashes or extra_hashes or len(dataset_hashes) != len(frozen_hashes):
        raise RuntimeError(
            "Dataset SHA parity check failed: "
            f"missing={len(missing_hashes)} extra={len(extra_hashes)} "
            f"dataset_hashes={len(dataset_hashes)} frozen_hashes={len(frozen_hashes)}"
        )

    await session.execute(
        text(
            "UPDATE data_dataset SET item_count = :item_count WHERE id = :dataset_id"
        ).bindparams(
            item_count=len(frozen_hashes),
            dataset_id=dataset_id,
        )
    )
    await session.commit()
    logger.info(
        "Verified SHA parity for dataset %s: %d frozen hashes == %d dataset hashes",
        dataset_id,
        len(frozen_hashes),
        len(dataset_hashes),
    )


async def seed(
    *,
    db_url: str,
    frozen_dir: Path,
    skip_if_exists: bool,
    dry_run: bool,
    materialize_missing: bool,
    sync_existing_version: bool,
    estimated_source_prefix: str,
) -> None:
    metadata_path = frozen_dir / "metadata.json"
    if not metadata_path.exists():
        logger.error("metadata.json not found at %s", metadata_path)
        raise SystemExit(1)

    with metadata_path.open(encoding="utf-8") as fh:
        meta = json.load(fh)

    version_tag: str = meta["version_tag"]
    expected_item_count: int = meta["item_count"]

    logger.info(
        "Frozen dataset: version_tag=%s  expected_items=%d",
        version_tag,
        expected_item_count,
    )

    # Load all frozen rows (text, sha256, split, label)
    frozen_rows = _load_frozen_rows(frozen_dir)
    logger.info("Loaded %d rows from frozen CSVs", len(frozen_rows))

    if not frozen_rows:
        logger.error("No rows loaded from frozen CSVs — aborting")
        raise SystemExit(1)

    is_sqlite = db_url.startswith("sqlite")

    def _uuid(u: uuid.UUID) -> str | uuid.UUID:
        return str(u) if is_sqlite else u

    def _dt(dt: "datetime") -> str | "datetime":
        return dt.isoformat() if is_sqlite else dt

    engine = create_async_engine(db_url, echo=False)
    async with async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )() as session:
        # Check if version already exists
        existing_dataset_id = await session.scalar(
            text("SELECT id FROM data_dataset WHERE version_tag = :vt").bindparams(
                vt=version_tag
            )
        )
        if existing_dataset_id and sync_existing_version and skip_if_exists:
            logger.error(
                "--skip-if-exists cannot be combined with --sync-existing-version"
            )
            raise SystemExit(1)

        if existing_dataset_id and not sync_existing_version:
            if skip_if_exists:
                logger.info(
                    "Dataset version_tag=%s already exists (id=%s) — skipping",
                    version_tag,
                    existing_dataset_id,
                )
                return
            logger.error(
                "Dataset version_tag=%s already exists. Use --skip-if-exists to skip or --sync-existing-version to add missing items.",
                version_tag,
            )
            raise SystemExit(1)

        # Query normalized messages whose sha256 is in our frozen set
        all_sha256s = [row.text_sha256 for row in frozen_rows]
        logger.info("Querying DB for %d sha256 hashes...", len(all_sha256s))

        matched = await _load_normalized_matches(session, all_sha256s)

        match_count = len(matched)
        miss_count = len(all_sha256s) - match_count
        match_pct = 100 * match_count / len(all_sha256s) if all_sha256s else 0

        logger.info(
            "Match result: %d/%d matched (%.1f%%), %d unmatched",
            match_count,
            len(all_sha256s),
            match_pct,
            miss_count,
        )

        # End the read-only transaction before local file processing so Neon does not
        # keep an idle transaction open while we compute provenance estimates.
        await session.rollback()

        if match_count == 0:
            logger.error(
                "Zero matches found — DB may not have annotations yet. Run normalize + annotate first."
            )
            raise SystemExit(1)

        if miss_count and materialize_missing:
            missing_rows = [
                row for row in frozen_rows if row.text_sha256 not in matched
            ]
            provenance_hashes = _load_provenance_hashes()
            estimated_distribution = Counter(
                _estimate_provenance_group(row.text_sha256, provenance_hashes)
                for row in missing_rows
            )
            logger.info(
                "Missing frozen rows eligible for reconstruction: %s",
                dict(sorted(estimated_distribution.items())),
            )
            if dry_run:
                logger.info(
                    "[dry-run] Would materialize %d missing frozen rows before dataset sync",
                    len(missing_rows),
                )
            else:
                await _materialize_missing_rows(
                    session,
                    missing_rows=missing_rows,
                    version_tag=version_tag,
                    estimated_source_prefix=estimated_source_prefix,
                    provenance_hashes=provenance_hashes,
                    now=datetime.now(timezone.utc),
                    to_uuid=_uuid,
                    to_datetime=_dt,
                )
                matched = await _load_normalized_matches(session, all_sha256s)
                match_count = len(matched)
                miss_count = len(all_sha256s) - match_count
                logger.info(
                    "Post-reconstruction match result: %d/%d matched, %d unmatched",
                    match_count,
                    len(all_sha256s),
                    miss_count,
                )

        if dry_run:
            projected_match_count = (
                len(all_sha256s) if materialize_missing else match_count
            )
            if existing_dataset_id and sync_existing_version:
                await session.rollback()
                existing_hashes = await _load_existing_dataset_hashes(
                    session, existing_dataset_id
                )
                pending_item_count = max(
                    0, projected_match_count - len(existing_hashes)
                )
                logger.info(
                    "[dry-run] Would sync existing dataset %s with %d additional data_dataset_item rows",
                    existing_dataset_id,
                    pending_item_count,
                )
            logger.info(
                "[dry-run] Would insert 1 data_dataset + %d data_dataset_item rows",
                projected_match_count,
            )
            return

        if miss_count:
            logger.error(
                "Cannot complete seeding: %d frozen rows still unmatched after optional reconstruction.",
                miss_count,
            )
            raise SystemExit(1)

        now = datetime.now(timezone.utc)
        dataset_id = existing_dataset_id
        if dataset_id is None:
            dataset_id = _uuid(uuid.uuid4())
            await session.execute(
                text(
                    "INSERT INTO data_dataset "
                    "(id, name, version_tag, target_usage, status, frozen_at, item_count, created_at) "
                    "VALUES (:id, :name, :vt, :usage, :status, :frozen_at, :item_count, :created_at)"
                ).bindparams(
                    id=dataset_id,
                    name="sicurre_training",
                    vt=version_tag,
                    usage="training",
                    status="frozen",
                    frozen_at=_dt(now),
                    item_count=match_count,
                    created_at=_dt(now),
                )
            )
            logger.info("Inserted data_dataset (id=%s)", dataset_id)
        else:
            logger.info("Syncing existing data_dataset (id=%s)", dataset_id)

        existing_dataset_hashes = await _load_existing_dataset_hashes(
            session, dataset_id
        )
        inserted_item_count = 0
        item_rows = []
        for row_order, row in enumerate(frozen_rows):
            nm_id = matched.get(row.text_sha256)
            if nm_id is None or row.text_sha256 in existing_dataset_hashes:
                continue
            item_rows.append(
                {
                    "id": _uuid(uuid.uuid4()),
                    "dataset_id": dataset_id,
                    "normalized_message_id": (
                        _uuid(nm_id) if isinstance(nm_id, uuid.UUID) else nm_id
                    ),
                    "split_name": row.split_name,
                    "sample_weight": 1.0,
                    "row_order": row_order,
                    "created_at": _dt(now),
                }
            )

        insert_batch_size = 500
        stmt = text(
            "INSERT INTO data_dataset_item "
            "(id, dataset_id, normalized_message_id, split_name, sample_weight, row_order, created_at) "
            "VALUES (:id, :dataset_id, :normalized_message_id, :split_name, :sample_weight, :row_order, :created_at)"
        )
        for i in range(0, len(item_rows), insert_batch_size):
            batch = item_rows[i : i + insert_batch_size]
            await session.execute(stmt, batch)
            await session.commit()
            inserted_item_count += len(batch)
            logger.info(
                "Inserted dataset items batch %d/%d",
                min(i + insert_batch_size, len(item_rows)),
                len(item_rows),
            )

        await _verify_dataset_sha_parity(
            session,
            dataset_id=dataset_id,
            frozen_rows=frozen_rows,
        )

    await engine.dispose()

    logger.info(
        "Done. Seeded dataset version_tag=%s with %d matched items and %d reconstructed rows.",
        version_tag,
        match_count,
        inserted_item_count if "inserted_item_count" in locals() else 0,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed frozen dataset into data_dataset + data_dataset_item."
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="SQLAlchemy async DB URL. Defaults to SICURRE_DATA_PLATFORM_DATABASE_URL.",
    )
    parser.add_argument(
        "--frozen-dir",
        type=Path,
        default=FROZEN_DIR,
        help="Path to current_frozen/ provenance directory.",
    )
    parser.add_argument(
        "--skip-if-exists",
        action="store_true",
        default=False,
        help="Exit cleanly if version_tag already exists in DB.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be inserted without writing to DB.",
    )
    parser.add_argument(
        "--materialize-missing",
        action="store_true",
        default=False,
        help="Create missing frozen rows as reconstructed curated records before seeding dataset items.",
    )
    parser.add_argument(
        "--sync-existing-version",
        action="store_true",
        default=False,
        help="If the dataset version already exists, add any missing dataset items instead of failing.",
    )
    parser.add_argument(
        "--estimated-source-prefix",
        default="reconstructed/current_frozen",
        help="Prefix for estimated source_system names when reconstructing missing rows.",
    )
    args = parser.parse_args()

    db_url = args.db_url
    if db_url is None:
        settings = get_settings()
        db_url = settings.data_platform_database_url

    asyncio.run(
        seed(
            db_url=db_url,
            frozen_dir=args.frozen_dir,
            skip_if_exists=args.skip_if_exists,
            dry_run=args.dry_run,
            materialize_missing=args.materialize_missing,
            sync_existing_version=args.sync_existing_version,
            estimated_source_prefix=args.estimated_source_prefix,
        )
    )


if __name__ == "__main__":
    main()
