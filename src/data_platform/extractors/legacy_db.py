"""Extractor service that connects to an external monolithic database to fetch threats."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from core.config import ROOT_DIR
from db.models import (
    DataIngestionRun,
    DataRawObject,
    DataRawRecord,
    DataSourceSystem,
    IngestionStatus,
    ObjectType,
    SourceType,
)
from db.queries import SourceSystemQueries
from data_platform.api.schemas import (
    DataSourceCreate,
    IngestionRunCreate,
)
from db.services.lineage import (
    IngestionRunService,
    SourceSystemService,
)
from data_platform.services.snapshot_storage import (
    SnapshotStore,
    SnapshotWriteResult,
    build_snapshot_store,
)

logger = logging.getLogger(__name__)

REPO_ROOT = ROOT_DIR
DEFAULT_LEGACY_DB_PATH = REPO_ROOT / "data" / "raw" / "db" / "external_threats.db"
DEFAULT_LEGACY_DB_URL = f"sqlite+aiosqlite:///{DEFAULT_LEGACY_DB_PATH}"

DEFAULT_LEGACY_SOURCE_NAME = "database-historical"
DEFAULT_LEGACY_SNAPSHOT_DIR = REPO_ROOT / "data" / "raw" / "db_historical"
DEFAULT_LEGACY_SNAPSHOT_PREFIX = "db_historical"

@dataclass(slots=True)
class LegacyDbIngestionResult:
    ingestion_run_id: str
    source_system_id: str
    snapshot_path: Path | None
    snapshot_storage_uri: str
    raw_object_count: int
    raw_record_count: int
    skipped_count: int
    total_extracted_count: int
    log_message: str


class LegacyDbConnector:
    """Client to query the external historical legacy database."""
    def __init__(self, db_url: str = DEFAULT_LEGACY_DB_URL) -> None:
        self.db_url = db_url

    async def fetch_threats(self) -> list[dict[str, Any]]:
        """Extract threat logs from the monolithic legacy database."""
        if not DEFAULT_LEGACY_DB_PATH.exists():
            raise FileNotFoundError(
                f"External DB not found at {DEFAULT_LEGACY_DB_PATH}. "
                "Run `make db-seed` first!"
            )
            
        engine = create_async_engine(self.db_url, echo=False)
        
        try:
            async with engine.connect() as conn:
                # We do a direct extraction from the monolithic DB tables
                query = text("""
                    SELECT 
                        t.id as threat_id,
                        t.message_id,
                        t.subject,
                        t.body_preview,
                        t.verdict,
                        t.confidence,
                        t.signals,
                        t.archetype,
                        t.source_dataset,
                        t.received_at,
                        u.email as user_email
                    FROM threat_log t
                    JOIN users u ON t.user_id = u.id
                """)
                result = await conn.execute(query)
                # Convert rows to dict mappings
                rows = result.mappings().fetchall()
                return [dict(row) for row in rows]
        finally:
            await engine.dispose()


class LegacyDbIngestionService:
    def __init__(
        self,
        *,
        connector: LegacyDbConnector | None = None,
        snapshot_dir: Path = DEFAULT_LEGACY_SNAPSHOT_DIR,
        snapshot_store: SnapshotStore | None = None,
        snapshot_prefix: str = DEFAULT_LEGACY_SNAPSHOT_PREFIX,
        source_name: str = DEFAULT_LEGACY_SOURCE_NAME,
    ) -> None:
        self.connector = connector or LegacyDbConnector()
        self.snapshot_dir = snapshot_dir
        self.snapshot_prefix = snapshot_prefix
        
        local_snapshot_root = (
            snapshot_dir.parent if snapshot_dir.name == snapshot_prefix else snapshot_dir
        )
        self.snapshot_store = snapshot_store or build_snapshot_store(
            local_root_dir=local_snapshot_root,
            repo_root=REPO_ROOT,
        )
        
        self.source_name = source_name
        self.source_service = SourceSystemService()
        self.ingestion_service = IngestionRunService()
        self.source_repository = SourceSystemQueries()

    async def run(
        self,
        session: AsyncSession,
        *,
        trigger_mode: str = "manual",
        started_at: datetime | None = None,
    ) -> LegacyDbIngestionResult:
        run_started_at = started_at or datetime.now(timezone.utc)
        source_system = await self._get_or_create_source_system(session)
        ingestion_run = await self.ingestion_service.create(
            session,
            IngestionRunCreate(
                source_system_id=source_system.id,
                started_at=run_started_at,
                status=IngestionStatus.RUNNING,
                trigger_mode=trigger_mode,
                log_message="Database historical extraction started",
            ),
        )

        try:
            entries = await self.connector.fetch_threats()
            total_extracted_count = len(entries)

            if not entries:
                ingestion_run.finished_at = datetime.now(timezone.utc)
                ingestion_run.status = IngestionStatus.COMPLETED
                ingestion_run.log_message = "DB extraction returned 0 entries"
                await session.commit()
                return self._empty_result(ingestion_run, source_system)

            new_entries = entries # Since we do full snapshot extractions
            skipped_count = 0

            # Write trace to Snapshot Store
            snapshot_payload = {
                "source": "External Legacy Database",
                "extracted_at": run_started_at.isoformat(),
                "records": []
            }
            # Need to format date strings for JSON serialization
            for entry in new_entries:
                entry_copy = dict(entry)
                if hasattr(entry_copy.get("received_at"), "isoformat"):
                    entry_copy["received_at"] = entry_copy["received_at"].isoformat()
                snapshot_payload["records"].append(entry_copy)

            snapshot_result = await self._write_snapshot(
                ingestion_run=ingestion_run,
                payload=snapshot_payload,
            )

            raw_object = self._build_raw_object(
                ingestion_run=ingestion_run,
                source_system=source_system,
                snapshot_result=snapshot_result,
                collected_at=run_started_at,
                entry_count=len(new_entries),
            )
            session.add(raw_object)
            await session.flush()

            raw_records = self._build_raw_records(
                raw_object=raw_object,
                entries=new_entries,
                source_system=source_system,
            )
            session.add_all(raw_records)

            log_message = (
                f"Historical DB extraction completed: "
                f"{len(raw_records)} entries extracted."
            )
            ingestion_run.finished_at = datetime.now(timezone.utc)
            ingestion_run.status = IngestionStatus.COMPLETED
            ingestion_run.raw_object_count = 1
            ingestion_run.raw_record_count = len(raw_records)
            ingestion_run.log_message = log_message
            await session.commit()

            return LegacyDbIngestionResult(
                ingestion_run_id=str(ingestion_run.id),
                source_system_id=str(source_system.id),
                snapshot_path=snapshot_result.local_path,
                snapshot_storage_uri=snapshot_result.storage_uri,
                raw_object_count=1,
                raw_record_count=len(raw_records),
                skipped_count=skipped_count,
                total_extracted_count=total_extracted_count,
                log_message=log_message,
            )
            
        except Exception as exc:
            ingestion_run.finished_at = datetime.now(timezone.utc)
            ingestion_run.status = IngestionStatus.FAILED
            ingestion_run.log_message = f"Historical DB ingestion failed: {exc}"
            await session.commit()
            raise

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _empty_result(
        self,
        run: DataIngestionRun,
        source: DataSourceSystem,
        *,
        skipped_count: int = 0,
        total_extracted_count: int = 0,
    ) -> LegacyDbIngestionResult:
        return LegacyDbIngestionResult(
            ingestion_run_id=str(run.id),
            source_system_id=str(source.id),
            snapshot_path=None,
            snapshot_storage_uri="",
            raw_object_count=0,
            raw_record_count=0,
            skipped_count=skipped_count,
            total_extracted_count=total_extracted_count,
            log_message=run.log_message or "",
        )

    @staticmethod
    def _entry_key(entry: dict[str, Any]) -> str:
        eid = entry.get("message_id") or entry.get("threat_id")
        return str(eid).strip()

    async def _get_or_create_source_system(self, session: AsyncSession) -> DataSourceSystem:
        source_system = await self.source_repository.get_by_name(session, self.source_name)
        if source_system is not None:
            return source_system

        return await self.source_service.create(
            session,
            DataSourceCreate(
                name=self.source_name,
                source_type=SourceType.SQL,
                description="Historical extraction from the external monolithic threat database",
                owner_name="Internal SecOps DB",
                legal_basis="historical_threat_intel",
                contains_personal_data=False,
                retention_days=365,
            ),
        )

    async def _write_snapshot(
        self,
        *,
        ingestion_run: DataIngestionRun,
        payload: dict[str, Any],
    ) -> SnapshotWriteResult:
        snapshot_bytes = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        date_str = ingestion_run.started_at.strftime("%Y%m%d")
        filename = f"db_historical_{date_str}_{ingestion_run.id}.json"
        
        object_key = self.snapshot_store.build_object_key(
            source_prefix=self.snapshot_prefix,
            filename=filename,
        )
        return await self.snapshot_store.write_snapshot(
            object_key=object_key,
            payload=snapshot_bytes,
            content_type="application/json",
        )

    def _build_raw_object(
        self,
        *,
        ingestion_run: DataIngestionRun,
        source_system: DataSourceSystem,
        snapshot_result: SnapshotWriteResult,
        collected_at: datetime,
        entry_count: int,
    ) -> DataRawObject:
        return DataRawObject(
            ingestion_run_id=ingestion_run.id,
            external_ref=f"sqlite://external_threats.db#run:{ingestion_run.id}",
            object_type=ObjectType.SQL_EXPORT,
            storage_uri=snapshot_result.storage_uri,
            source_format="json",
            content_hash=snapshot_result.content_hash,
            size_bytes=snapshot_result.size_bytes,
            source_metadata={
                "source_name": source_system.name,
                "entry_count": entry_count,
            },
            collected_at=collected_at,
        )

    def _build_raw_records(
        self,
        *,
        raw_object: DataRawObject,
        entries: list[dict[str, Any]],
        source_system: DataSourceSystem,
    ) -> list[DataRawRecord]:
        extracted_at = datetime.now(timezone.utc)
        raw_records: list[DataRawRecord] = []

        for index, entry in enumerate(entries, start=1):
            record_key = self._entry_key(entry)
            
            # Map external schema to sicurre standard raw text
            subject = entry.get("subject", "")
            body = entry.get("body_preview", "")
            full_text = f"{subject}\n\n{body}" if subject else body

            label = 1 if entry.get("verdict") == "phishing" else 0
            
            enriched = {
                "subject": subject,
                "body": body,
                "text": full_text,
                "label": label,
                "confidence": entry.get("confidence"),
                "source": entry.get("source_dataset"),
                "archetype": entry.get("archetype"),
                "signals": entry.get("signals"),
            }

            raw_content = json.dumps(
                enriched, ensure_ascii=False, sort_keys=True,
            )
            is_usable = bool(full_text)
            rejection_reason = None if is_usable else "missing_body"

            raw_records.append(
                DataRawRecord(
                    raw_object_id=raw_object.id, source_system_id=source_system.id,
                    record_key=record_key,
                    raw_content=raw_content,
                    detected_language="fr",
                    is_usable=is_usable,
                    rejection_reason=rejection_reason,
                    extracted_at=extracted_at,
                )
            )

        return raw_records
