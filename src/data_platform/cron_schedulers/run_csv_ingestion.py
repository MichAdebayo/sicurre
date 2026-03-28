"""Bulk loader for static machine learning text datasets.

This script recursively scans a directory for CSV files containing the unified
data schema: [text, label, source, language].

It dynamically looks up (or creates) the SourceSystem based on the `source` column,
creates an IngestionRun, registers the CSV file as a DataRawObject, and bulk-inserts
all rows as DataRawRecords into the Sicurre database.

Usage::

    uv run --group backend python backend/scripts/csv_ingestion.py --dir data/raw/csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Increase CSV field size limit for massive ML text blocks (e.g., Enron emails)
csv.field_size_limit(sys.maxsize)

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import get_settings  # noqa: E402
from core.database import Base  # noqa: E402
from db.models import (  # noqa: E402
    DataIngestionRun,
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


def hash_text_for_dedup(text: str) -> str:
    """Generate a SHA-256 hash using the first 300 characters of the text."""
    if not text:
        return "empty"
    return hashlib.sha256(text[:300].encode("utf-8", errors="ignore")).hexdigest()


async def get_or_create_source_system(
    session: AsyncSession,
    repo: SourceSystemQueries,
    source_machine_name: str,
) -> DataSourceSystem:
    # Try looking up exactly by name
    query = select(DataSourceSystem).where(
        DataSourceSystem.name == source_machine_name
    )
    result = await session.execute(query)
    source_sys = result.scalar_one_or_none()
    
    if source_sys:
        return source_sys

    # Infer a display name
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
) -> int:
    """Read a CSV file and insert it into the database."""
    logger.info("Processing file: %s", file_path)

    try:
        with file_path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception as e:
        logger.error("Failed to read %s: %s", file_path, e)
        return 0

    if not rows:
        logger.warning("File is empty or has no rows. Skipping.")
        return 0

    # Extract source identifier from the first row. Fallback to filename.
    first_row = rows[0]
    source_machine_name = first_row.get("source", "").strip()
    if not source_machine_name:
        source_machine_name = file_path.stem.lower()

    # Get or create SourceSystem
    source_sys = await get_or_create_source_system(session, source_repo, source_machine_name)

    file_stat = file_path.stat()
    file_content_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
    external_ref = f"local://{file_path.name}"
    
    # Idempotency check: Have we processed this EXACT file before?
    query = select(DataRawObject).where(
        DataRawObject.external_ref == external_ref,
        DataRawObject.content_hash == file_content_hash
    )
    result = await session.execute(query)
    if result.scalar_one_or_none():
        logger.info("File %s is already ingested (hash matches). Skipping.", file_path.name)
        return 0

    # Note: We group files by ingestion run. A single file load is one run.
    started_at = datetime.now(timezone.utc)
    ingestion_run = await run_repo.create(
        session,
        payload=IngestionRunCreate(
            source_system_id=source_sys.id,
            trigger_mode="manual",
            status="pending",
            started_at=started_at,
        ),
    )

    # Represent the CSV file as a RawObject
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
    await session.flush()  # To get raw_object.id

    # Create RawRecord for each row
    extracted_at = datetime.now(timezone.utc)
    records_to_add: list[DataRawRecord] = []
    
    raw_keys_seen = set()

    for idx, row in enumerate(rows, start=1):
        text = str(row.get("text", "")).strip()
        label = str(row.get("label", "")).strip()
        lang = str(row.get("language", "")).strip() or None
        
        # Build deduplication key
        record_key = hash_text_for_dedup(text) if text else f"empty-text-{idx}"
        
        # Intra-file deduplication (if a CSV has duplicated texts right inside it)
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
                record_key=record_key,
                raw_content=raw_content,
                detected_language=lang,
                is_usable=is_usable,
                rejection_reason=rejection_reason,
                extracted_at=extracted_at,
            )
        )

    # Chunk insert into database (10k at a time to prevent SQLite parameter limits)
    chunk_size = 5000
    for i in range(0, len(records_to_add), chunk_size):
        chunk = records_to_add[i : i + chunk_size]
        session.add_all(chunk)

    # Mark ingestion as complete
    ingestion_run.finished_at = datetime.now(timezone.utc)
    ingestion_run.status = "completed"
    ingestion_run.raw_record_count = len(records_to_add)

    # Actually commit everything to the DB
    try:
        await session.commit()
        logger.info(
            "Successfully inserted %d unique records for %s", 
            len(records_to_add), 
            file_path.name
        )
        return len(records_to_add)
    except Exception as e:
        await session.rollback()
        # Fall back to doing a manual merge if there are unique constraint violations 
        # (meaning the text is already in the database from a previous ingestion!)
        logger.warning(
            "Constraint violation (likely duplicate DataRawRecord record_key). Retrying with merge... (%s)", e
        )
        
        inserted_count = 0
        for record in records_to_add:
            try:
                # We do a flush per record. If it fails uniqueness, we rollback and continue.
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
            file_path.name
        )
        return inserted_count


async def main(base_dir: str) -> None:
    settings = get_settings()
    db_url = settings.database_url
    logger.info("Using database: %s", db_url)

    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession,
    )

    source_repo = SourceSystemQueries()
    run_repo = IngestionRunQueries()

    search_dir = Path(base_dir).resolve()
    if not search_dir.exists() or not search_dir.is_dir():
        logger.error("Directory not found: %s", search_dir)
        sys.exit(1)

    # Find all CSV files recursively
    csv_files = list(search_dir.rglob("*.csv"))
    if not csv_files:
        logger.warning("No .csv files found in %s", search_dir)
        return

    logger.info("Found %d CSV files to process.", len(csv_files))

    total_inserted = 0
    for csv_file in csv_files:
        async with session_factory() as session:
            inserted = await ingest_csv_file(csv_file, session, source_repo, run_repo)
            total_inserted += inserted

    logger.info("All CSV files processed. Total new records inserted: %d", total_inserted)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest static CSV datasets.")
    parser.add_argument(
        "--dir",
        type=str,
        default="data/raw/csv",
        help="Directory to recursively search for CSV files.",
    )
    args = parser.parse_args()

    asyncio.run(main(args.dir))
