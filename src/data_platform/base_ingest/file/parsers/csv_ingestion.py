from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[5]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

csv.field_size_limit(sys.maxsize)

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import get_settings  # noqa: E402
from core.database import Base  # noqa: E402
from core.trace_logger import SemanticTraceLogger  # noqa: E402
from db.models import (  # noqa: E402
    DataRawObject,
    DataRawRecord,
    DataSourceSystem,
)
from db.queries import (  # noqa: E402
    IngestionRunQueries,
    SourceSystemQueries,
)
from data_platform.api.schemas import (  # noqa: E402
    DataSourceCreate,
    IngestionRunCreate,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

CSV_REQUIRED_COLUMNS: frozenset[str] = frozenset({"text", "label"})
CSV_OPTIONAL_COLUMNS: frozenset[str] = frozenset({"source", "language"})
CSV_TEXT_ONLY_HISTORICAL_FILES: frozenset[str] = frozenset(
    {"data-en-hi-de-fr.csv", "kaggle_multilingual_spam.csv"}
)


@dataclass(frozen=True, slots=True)
class CsvIngestionResult:
    file_path: Path
    inserted_count: int
    status: str


def hash_text_for_dedup(text: str) -> str:
    if not text:
        return "empty"
    return hashlib.sha256(text[:300].encode("utf-8", errors="ignore")).hexdigest()


def _normalize_csv_fieldnames(fieldnames: list[str] | None) -> tuple[str, ...]:
    return tuple(
        field.strip() for field in (fieldnames or []) if field and field.strip()
    )


def _uses_text_only_historical_schema(
    file_path: Path, fieldnames: tuple[str, ...]
) -> bool:
    return (
        file_path.name in CSV_TEXT_ONLY_HISTORICAL_FILES
        and "text" in fieldnames
        and "labels" in fieldnames
    )


def _validate_csv_schema(file_path: Path, fieldnames: tuple[str, ...]) -> bool:
    if _uses_text_only_historical_schema(file_path, fieldnames):
        logger.warning(
            "CSV file %s uses the historical multilingual schema. Ingesting text-only rows with blank labels.",
            file_path.name,
        )
        return True

    missing_required = sorted(CSV_REQUIRED_COLUMNS.difference(fieldnames))
    if missing_required:
        logger.error(
            "Skipping %s because required CSV columns are missing: %s. Expected required columns: %s. Optional columns: %s.",
            file_path.name,
            ", ".join(missing_required),
            ", ".join(sorted(CSV_REQUIRED_COLUMNS)),
            ", ".join(sorted(CSV_OPTIONAL_COLUMNS)),
        )
        return False

    missing_optional = sorted(CSV_OPTIONAL_COLUMNS.difference(fieldnames))
    if missing_optional:
        logger.warning(
            "CSV file %s is missing optional columns: %s. Using filename or null fallbacks where available.",
            file_path.name,
            ", ".join(missing_optional),
        )

    return True


def _validate_csv_rows(
    file_path: Path,
    rows: list[dict[str, Any]],
    *,
    allow_blank_labels: bool = False,
) -> bool:
    if allow_blank_labels:
        return True

    blank_label_rows = [
        index
        for index, row in enumerate(rows, start=1)
        if not str(row.get("label", "")).strip()
    ]
    if blank_label_rows:
        preview = ", ".join(str(index) for index in blank_label_rows[:5])
        suffix = "" if len(blank_label_rows) <= 5 else ", ..."
        logger.error(
            "Skipping %s because label values are blank for row(s): %s%s.",
            file_path.name,
            preview,
            suffix,
        )
        return False

    return True


async def get_or_create_source_system(
    session: AsyncSession,
    repo: SourceSystemQueries,
    source_machine_name: str,
) -> DataSourceSystem:
    query = select(DataSourceSystem).where(DataSourceSystem.name == source_machine_name)
    result = await session.execute(query)
    source_sys = result.scalar_one_or_none()

    if source_sys:
        return source_sys

    display_name = source_machine_name.replace("_", " ").title()

    logger.info("Creating new SourceSystem: %s", source_machine_name)
    return await repo.create(
        session,
        payload=DataSourceCreate(
            name=source_machine_name,
            source_type="file",
            description=f"Automated CSV Dataset loader for {display_name}",
        ),
    )


async def ingest_csv_file(
    file_path: Path,
    session: AsyncSession,
    source_repo: SourceSystemQueries,
    run_repo: IngestionRunQueries,
    *,
    trigger_mode: str = "manual",
    trace: SemanticTraceLogger | None = None,
) -> CsvIngestionResult:
    logger.info("Processing file: %s", file_path)
    if trace is not None:
        trace.trace(
            stage="ingestion",
            status="start",
            message=f"CSV ingestion starting for {file_path.name}",
            entity_type="csv_file",
            entity_id=file_path.name,
        )

    try:
        with file_path.open(encoding="utf-8") as file_handle:
            reader = csv.DictReader(file_handle)
            fieldnames = _normalize_csv_fieldnames(reader.fieldnames)
            rows = list(reader)
    except Exception as exc:
        logger.error("Failed to read %s: %s", file_path, exc)
        if trace is not None:
            trace.trace(
                stage="ingestion",
                status="failed",
                message=f"CSV read failed for {file_path.name}: {exc}",
                entity_type="csv_file",
                entity_id=file_path.name,
            )
        return CsvIngestionResult(
            file_path=file_path, inserted_count=0, status="read_error"
        )

    if not rows:
        logger.warning("File is empty or has no rows. Skipping.")
        if trace is not None:
            trace.trace(
                stage="ingestion",
                status="skipped",
                message=f"CSV file {file_path.name} is empty",
                entity_type="csv_file",
                entity_id=file_path.name,
            )
        return CsvIngestionResult(file_path=file_path, inserted_count=0, status="empty")

    file_stat = file_path.stat()
    file_content_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
    external_ref = f"local://{file_path.name}"

    query = select(DataRawObject).where(
        DataRawObject.external_ref == external_ref,
        DataRawObject.content_hash == file_content_hash,
    )
    result = await session.execute(query)
    if result.scalar_one_or_none():
        logger.info(
            "File %s is already ingested (hash matches). Skipping.", file_path.name
        )
        if trace is not None:
            trace.trace(
                stage="ingestion",
                status="skipped",
                message=f"CSV file {file_path.name} unchanged; skipping",
                entity_type="csv_file",
                entity_id=file_path.name,
            )
        return CsvIngestionResult(
            file_path=file_path, inserted_count=0, status="skipped_unchanged"
        )

    if not _validate_csv_schema(file_path, fieldnames):
        if trace is not None:
            trace.trace(
                stage="ingestion",
                status="skipped",
                message=f"CSV file {file_path.name} has invalid schema",
                entity_type="csv_file",
                entity_id=file_path.name,
            )
        return CsvIngestionResult(
            file_path=file_path, inserted_count=0, status="skipped_invalid_schema"
        )

    uses_text_only_historical_schema = _uses_text_only_historical_schema(
        file_path, fieldnames
    )

    if not _validate_csv_rows(
        file_path,
        rows,
        allow_blank_labels=uses_text_only_historical_schema,
    ):
        if trace is not None:
            trace.trace(
                stage="ingestion",
                status="skipped",
                message=f"CSV file {file_path.name} has invalid rows",
                entity_type="csv_file",
                entity_id=file_path.name,
            )
        return CsvIngestionResult(
            file_path=file_path, inserted_count=0, status="skipped_invalid_rows"
        )

    first_row = rows[0]
    source_machine_name = first_row.get("source", "").strip() or file_path.stem.lower()

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
        source_format="csv",
        content_hash=file_content_hash,
        size_bytes=file_stat.st_size,
        source_metadata={
            "filename": file_path.name,
            "entry_count": len(rows),
        },
        collected_at=started_at,
    )
    session.add(raw_object)
    await session.flush()

    extracted_at = datetime.now(timezone.utc)
    records_to_add: list[DataRawRecord] = []
    raw_keys_seen: set[str] = set()

    for idx, row in enumerate(rows, start=1):
        text = str(row.get("text", "")).strip()
        if uses_text_only_historical_schema:
            label = ""
            lang = None
        else:
            label = str(row.get("label", "")).strip()
            lang = str(row.get("language", "")).strip() or None
        record_key = hash_text_for_dedup(text) if text else f"empty-text-{idx}"

        if record_key in raw_keys_seen:
            continue
        raw_keys_seen.add(record_key)

        is_usable = bool(text)
        rejection_reason = None if is_usable else "empty_text"

        raw_content = json.dumps(
            {
                "text": text,
                "label": label,
                "source": source_machine_name,
                "language": lang,
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
                detected_language=lang,
                is_usable=is_usable,
                rejection_reason=rejection_reason,
                extracted_at=extracted_at,
            )
        )

    chunk_size = 5000
    for index in range(0, len(records_to_add), chunk_size):
        chunk = records_to_add[index : index + chunk_size]
        session.add_all(chunk)

    ingestion_run.finished_at = datetime.now(timezone.utc)
    ingestion_run.status = "completed"
    ingestion_run.raw_record_count = len(records_to_add)

    try:
        await session.commit()
        logger.info(
            "Successfully inserted %d unique records for %s",
            len(records_to_add),
            file_path.name,
        )
        if trace is not None:
            trace.trace(
                stage="ingestion",
                status="success",
                message=f"CSV file {file_path.name} ingested",
                entity_type="csv_file",
                entity_id=file_path.name,
                metrics={"inserted": len(records_to_add)},
            )
        return CsvIngestionResult(
            file_path=file_path, inserted_count=len(records_to_add), status="ingested"
        )
    except Exception as exc:
        await session.rollback()
        logger.warning(
            "Constraint violation (likely duplicate DataRawRecord record_key). Retrying with merge... (%s)",
            exc,
        )

        inserted_count = 0
        for record in records_to_add:
            try:
                async with session.begin_nested():
                    session.add(record)
                inserted_count += 1
            except Exception:
                pass

        ingestion_run.raw_record_count = inserted_count
        await session.commit()
        logger.info(
            "Merge complete. Inserted %d unique new records for %s.",
            inserted_count,
            file_path.name,
        )
        if trace is not None:
            trace.trace(
                stage="ingestion",
                status="success",
                message=f"CSV file {file_path.name} ingested with merge fallback",
                entity_type="csv_file",
                entity_id=file_path.name,
                metrics={"inserted": inserted_count},
            )
        return CsvIngestionResult(
            file_path=file_path,
            inserted_count=inserted_count,
            status="ingested_merged",
        )


async def run_ingestion(base_dir: str, *, trigger_mode: str = "manual") -> None:
    settings = get_settings()
    db_url = settings.database_url
    logger.info("Using database: %s", db_url)
    trace = SemanticTraceLogger(
        parent_type="File",
        child_target="CSV Ingestion",
        domain="data_platform",
    )
    trace.trace(
        stage="orchestration",
        status="start",
        message="CSV ingestion run starting",
        metrics={"trigger_mode": trigger_mode},
    )

    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(
            engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

        source_repo = SourceSystemQueries()
        run_repo = IngestionRunQueries()

        search_dir = Path(base_dir).resolve()
        if not search_dir.exists() or not search_dir.is_dir():
            logger.error("Directory not found: %s", search_dir)
            trace.trace(
                stage="orchestration",
                status="failed",
                message=f"CSV source directory not found: {search_dir}",
            )
            raise SystemExit(1)

        csv_files = list(search_dir.rglob("*.csv"))
        if not csv_files:
            logger.warning("No .csv files found in %s", search_dir)
            trace.trace(
                stage="orchestration",
                status="skipped",
                message=f"No CSV files found in {search_dir}",
            )
            return

        logger.info("Found %d CSV files to process.", len(csv_files))

        total_inserted = 0
        status_counts: dict[str, int] = {
            "ingested": 0,
            "ingested_merged": 0,
            "skipped_unchanged": 0,
            "skipped_invalid_schema": 0,
            "skipped_invalid_rows": 0,
            "empty": 0,
            "read_error": 0,
        }
        for csv_file in csv_files:
            async with session_factory() as session:
                result = await ingest_csv_file(
                    csv_file,
                    session,
                    source_repo,
                    run_repo,
                    trigger_mode=trigger_mode,
                    trace=trace,
                )
                total_inserted += result.inserted_count
                status_counts[result.status] = status_counts.get(result.status, 0) + 1

        logger.info(
            "All CSV files processed. Total new records inserted: %d", total_inserted
        )
        logger.info(
            "CSV ingestion summary: ingested=%d, ingested_merged=%d, skipped_unchanged=%d, skipped_invalid_schema=%d, skipped_invalid_rows=%d, empty=%d, read_error=%d",
            status_counts["ingested"],
            status_counts["ingested_merged"],
            status_counts["skipped_unchanged"],
            status_counts["skipped_invalid_schema"],
            status_counts["skipped_invalid_rows"],
            status_counts["empty"],
            status_counts["read_error"],
        )
        trace.trace(
            stage="orchestration",
            status="success",
            message="CSV ingestion run completed",
            metrics={
                "files": len(csv_files),
                "inserted": total_inserted,
                "skipped_unchanged": status_counts["skipped_unchanged"],
                "invalid_schema": status_counts["skipped_invalid_schema"],
                "invalid_rows": status_counts["skipped_invalid_rows"],
            },
        )
    except Exception as exc:
        trace.trace(
            stage="orchestration",
            status="failed",
            message=f"CSV ingestion run failed: {exc}",
        )
        raise
    finally:
        await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest static CSV datasets.")
    parser.add_argument(
        "--dir",
        type=str,
        default="data/raw/file/csv",
        help="Directory to recursively search for CSV files.",
    )
    parser.add_argument(
        "--trigger",
        default="manual",
        choices=["manual", "scheduled"],
        help="Trigger mode written to created ingestion runs.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    await run_ingestion(args.dir, trigger_mode=args.trigger)


if __name__ == "__main__":
    asyncio.run(main())
