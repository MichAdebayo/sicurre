"""Incremental file ingestion from recurring R2 file prefixes.

This module polls the user-managed recurring file prefixes and ingests them
directly into the platform:

- raw-snapshots/cron/file/csv -> recurring CSV datasets
- raw-snapshots/cron/file/txt -> exported TXT email bundles

The uploaded objects already live in R2, so the ingestion records keep their
original ``r2://`` storage URI instead of creating a second derived snapshot.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.config import get_settings  # noqa: E402
from core.database import Base  # noqa: E402
from core.trace_logger import SemanticTraceLogger  # noqa: E402
from data_platform.api.schemas import IngestionRunCreate  # noqa: E402
from data_platform.base_ingest.file.parsers.csv_ingestion import (  # noqa: E402
    get_or_create_source_system,
    ingest_csv_bytes,
)
from data_platform.base_ingest.file.parsers.txt_email_ingestion import (  # noqa: E402
    TxtEmailRecord,
    parse_txt_emails_from_bytes,
)
from data_platform.services.shared.r2_read_client import R2ReadClient  # noqa: E402
from db.models import DataRawObject, DataRawRecord  # noqa: E402
from db.queries import IngestionRunQueries, SourceSystemQueries  # noqa: E402

logger = logging.getLogger(__name__)

CRON_FILE_CSV_PREFIX = os.environ.get(
    "SICURRE_FILE_CRON_CSV_PREFIX",
    os.environ.get(
        "SICURRE_FILE_DROPZONE_CSV_PREFIX",
        "raw-snapshots/cron/file/csv",
    ),
)
CRON_FILE_TXT_PREFIX = os.environ.get(
    "SICURRE_FILE_CRON_TXT_PREFIX",
    os.environ.get(
        "SICURRE_FILE_DROPZONE_TXT_PREFIX",
        "raw-snapshots/cron/file/txt",
    ),
)


@dataclass(frozen=True, slots=True)
class CronFileObject:
    r2_key: str
    filename: str
    fmt: str
    source_url: str
    data: bytes
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class FileCronIngestionResult:
    processed_files: int
    inserted_records: int
    skipped_files: int
    rows: list[dict[str, Any]]


def _enumerate_cron_file_objects(r2: R2ReadClient) -> list[CronFileObject]:
    entries: list[CronFileObject] = []

    for obj in r2.list_objects(CRON_FILE_CSV_PREFIX, suffix=".csv"):
        data = r2.download_bytes(obj.key)
        entries.append(
            CronFileObject(
                r2_key=obj.key,
                filename=obj.key.rsplit("/", 1)[-1],
                fmt="csv",
                source_url=f"r2://{r2.bucket}/{obj.key}",
                data=data,
                sha256=hashlib.sha256(data).hexdigest(),
                size_bytes=len(data),
            )
        )

    for obj in r2.list_objects(CRON_FILE_TXT_PREFIX, suffix=".txt"):
        data = r2.download_bytes(obj.key)
        entries.append(
            CronFileObject(
                r2_key=obj.key,
                filename=obj.key.rsplit("/", 1)[-1],
                fmt="txt",
                source_url=f"r2://{r2.bucket}/{obj.key}",
                data=data,
                sha256=hashlib.sha256(data).hexdigest(),
                size_bytes=len(data),
            )
        )

    entries.sort(key=lambda entry: entry.r2_key)
    return entries


async def _cron_file_content_already_ingested(
    session: AsyncSession,
    *,
    sha256: str,
    source_url: str,
) -> bool:
    stmt = select(DataRawObject.id).where(
        DataRawObject.content_hash == sha256,
        DataRawObject.storage_uri == source_url,
    )
    return await session.scalar(stmt) is not None


async def _persist_txt_records(
    *,
    entry: CronFileObject,
    parsed_records: list[TxtEmailRecord],
    session: AsyncSession,
    source_repo: SourceSystemQueries,
    run_repo: IngestionRunQueries,
    trigger_mode: str,
    trace: SemanticTraceLogger,
) -> dict[str, Any]:
    if not parsed_records:
        return {
            "filename": entry.filename,
            "fmt": entry.fmt,
            "inserted": 0,
            "status": "empty",
        }

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
            status="running",
            started_at=started_at,
        ),
    )

    raw_object = DataRawObject(
        ingestion_run_id=ingestion_run.id,
        external_ref=entry.source_url,
        object_type="file",
        storage_uri=entry.source_url,
        source_format=entry.fmt,
        content_hash=entry.sha256,
        size_bytes=entry.size_bytes,
        source_metadata={
            "filename": entry.filename,
            "r2_key": entry.r2_key,
            "entry_count": len(parsed_records),
            "ingestion_family": "cron_file",
        },
        collected_at=started_at,
    )
    session.add(raw_object)
    await session.flush()

    extracted_at = datetime.now(timezone.utc)
    records_to_add: list[DataRawRecord] = []
    raw_keys_seen: set[str] = set()

    for index, record in enumerate(parsed_records, start=1):
        text = record.text.strip() if record.text else ""
        record_key = (
            hashlib.sha256(text[:300].encode("utf-8", errors="ignore")).hexdigest()
            if text
            else f"empty-text-{index}"
        )
        if record_key in raw_keys_seen:
            continue
        raw_keys_seen.add(record_key)

        raw_content = json.dumps(
            {
                "text": text,
                "label": record.label,
                "source": record.source,
                "language": record.language,
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
                detected_language=record.language,
                is_usable=bool(text),
                rejection_reason=None if text else "empty_text",
                extracted_at=extracted_at,
            )
        )

    for offset in range(0, len(records_to_add), 5_000):
        session.add_all(records_to_add[offset : offset + 5_000])

    ingestion_run.finished_at = datetime.now(timezone.utc)
    ingestion_run.status = "completed"
    ingestion_run.raw_object_count = 1
    ingestion_run.raw_record_count = len(records_to_add)
    ingestion_run.log_message = f"TXT cron ingestion completed: {len(records_to_add)} record(s) from {entry.filename}"
    await session.commit()

    trace.trace(
        stage="ingestion",
        status="success",
        message=f"TXT cron file {entry.filename} ingested",
        entity_type="cron_file",
        entity_id=entry.r2_key,
        metrics={"inserted": len(records_to_add)},
    )
    return {
        "filename": entry.filename,
        "fmt": entry.fmt,
        "inserted": len(records_to_add),
        "status": "ingested",
    }


async def run_cron_file_ingestion(
    *,
    trigger_mode: str = "scheduled",
) -> FileCronIngestionResult:
    r2 = R2ReadClient()
    entries = _enumerate_cron_file_objects(r2)
    logger.info(
        "File cron poll discovered %d object(s) under %s and %s",
        len(entries),
        CRON_FILE_CSV_PREFIX,
        CRON_FILE_TXT_PREFIX,
    )

    if not entries:
        return FileCronIngestionResult(
            processed_files=0,
            inserted_records=0,
            skipped_files=0,
            rows=[],
        )

    settings = get_settings()
    engine = create_async_engine(settings.data_platform_database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    source_repo = SourceSystemQueries()
    run_repo = IngestionRunQueries()
    trace = SemanticTraceLogger(
        parent_type="File",
        child_target="File Cron Ingestion",
        domain="data_platform",
    )
    trace.trace(
        stage="orchestration",
        status="start",
        message="File cron ingestion run starting",
        metrics={"files": len(entries), "trigger_mode": trigger_mode},
    )

    rows: list[dict[str, Any]] = []
    inserted_records = 0
    skipped_files = 0

    try:
        for entry in entries:
            async with session_factory() as session:
                if await _cron_file_content_already_ingested(
                    session,
                    sha256=entry.sha256,
                    source_url=entry.source_url,
                ):
                    rows.append(
                        {
                            "filename": entry.filename,
                            "fmt": entry.fmt,
                            "inserted": 0,
                            "status": "skipped_duplicate_content",
                        }
                    )
                    skipped_files += 1
                    continue

                if entry.fmt == "csv":
                    result = await ingest_csv_bytes(
                        entry.data,
                        entry.filename,
                        entry.source_url,
                        entry.source_url,
                        session,
                        source_repo,
                        run_repo,
                        trigger_mode=trigger_mode,
                        trace=trace,
                    )
                    row = {
                        "filename": entry.filename,
                        "fmt": entry.fmt,
                        "inserted": result.inserted_count,
                        "status": result.status,
                    }
                else:
                    parsed_records = parse_txt_emails_from_bytes(
                        entry.data,
                        entry.filename.rsplit(".", 1)[0].lower(),
                    )
                    row = await _persist_txt_records(
                        entry=entry,
                        parsed_records=parsed_records,
                        session=session,
                        source_repo=source_repo,
                        run_repo=run_repo,
                        trigger_mode=trigger_mode,
                        trace=trace,
                    )

                rows.append(row)
                inserted_records += int(row["inserted"])
                if str(row["status"]).startswith("skipped"):
                    skipped_files += 1

        trace.trace(
            stage="orchestration",
            status="success",
            message="File cron ingestion run completed",
            metrics={
                "files": len(entries),
                "inserted": inserted_records,
                "skipped_files": skipped_files,
            },
        )
        return FileCronIngestionResult(
            processed_files=len(entries),
            inserted_records=inserted_records,
            skipped_files=skipped_files,
            rows=rows,
        )
    finally:
        await engine.dispose()


async def run_dropzone_ingestion(
    *,
    trigger_mode: str = "scheduled",
) -> FileCronIngestionResult:
    """Backward-compatible alias for the old dropzone naming."""
    return await run_cron_file_ingestion(trigger_mode=trigger_mode)
