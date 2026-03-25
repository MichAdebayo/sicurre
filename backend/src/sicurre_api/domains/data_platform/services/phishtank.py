from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from sicurre_api.core.config import BACKEND_ROOT
from sicurre_api.domains.data_platform.models import (
    DataIngestionRun,
    DataRawObject,
    DataRawRecord,
    DataSourceSystem,
    IngestionStatus,
    ObjectType,
    SourceType,
)
from sicurre_api.domains.data_platform.repositories import SourceSystemRepository
from sicurre_api.domains.data_platform.schemas import (
    DataSourceCreate,
    IngestionRunCreate,
)
from sicurre_api.domains.data_platform.services.lineage import (
    IngestionRunService,
    SourceSystemService,
)


REPO_ROOT = BACKEND_ROOT.parent
DEFAULT_PHISHTANK_FEED_URL = "https://data.phishtank.com/data/online-valid.json"
DEFAULT_PHISHTANK_SOURCE_NAME = "phishtank-online-valid"
DEFAULT_PHISHTANK_SNAPSHOT_DIR = REPO_ROOT / "data" / "raw" / "api" / "phishtank"


@dataclass(slots=True)
class PhishTankIngestionResult:
    ingestion_run_id: str
    source_system_id: str
    snapshot_path: Path
    raw_object_count: int
    raw_record_count: int


class PhishTankFeedClient:
    def __init__(
        self,
        *,
        feed_url: str = DEFAULT_PHISHTANK_FEED_URL,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.feed_url = feed_url
        self.timeout_seconds = timeout_seconds

    async def fetch_entries(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(self.feed_url)
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, list):
            raise ValueError("PhishTank feed must return a JSON array")

        return [entry for entry in payload if isinstance(entry, dict)]


class PhishTankIngestionService:
    def __init__(
        self,
        *,
        feed_client: PhishTankFeedClient | None = None,
        fetch_entries: Callable[[], Awaitable[list[dict[str, Any]]]] | None = None,
        snapshot_dir: Path = DEFAULT_PHISHTANK_SNAPSHOT_DIR,
        source_name: str = DEFAULT_PHISHTANK_SOURCE_NAME,
    ) -> None:
        self.feed_client = feed_client or PhishTankFeedClient()
        self.fetch_entries = fetch_entries or self.feed_client.fetch_entries
        self.snapshot_dir = snapshot_dir
        self.source_name = source_name
        self.source_service = SourceSystemService()
        self.ingestion_service = IngestionRunService()
        self.source_repository = SourceSystemRepository()

    async def run(
        self,
        session: AsyncSession,
        *,
        trigger_mode: str = "scheduled",
        started_at: datetime | None = None,
    ) -> PhishTankIngestionResult:
        run_started_at = started_at or datetime.now(timezone.utc)
        source_system = await self._get_or_create_source_system(session)
        ingestion_run = await self.ingestion_service.create(
            session,
            IngestionRunCreate(
                source_system_id=source_system.id,
                started_at=run_started_at,
                status=IngestionStatus.RUNNING,
                trigger_mode=trigger_mode,
                log_message="PhishTank ingestion started",
            ),
        )

        try:
            entries = await self.fetch_entries()
            snapshot_path, content_hash, size_bytes = await self._write_snapshot(
                ingestion_run=ingestion_run,
                entries=entries,
            )
            raw_object = self._build_raw_object(
                ingestion_run=ingestion_run,
                source_system=source_system,
                snapshot_path=snapshot_path,
                content_hash=content_hash,
                size_bytes=size_bytes,
                collected_at=run_started_at,
                entry_count=len(entries),
            )
            session.add(raw_object)
            await session.flush()

            raw_records = self._build_raw_records(
                raw_object=raw_object, entries=entries
            )
            session.add_all(raw_records)

            ingestion_run.finished_at = datetime.now(timezone.utc)
            ingestion_run.status = IngestionStatus.COMPLETED
            ingestion_run.raw_object_count = 1
            ingestion_run.raw_record_count = len(raw_records)
            ingestion_run.log_message = (
                f"PhishTank ingestion completed with {len(raw_records)} records"
            )
            await session.commit()

            return PhishTankIngestionResult(
                ingestion_run_id=str(ingestion_run.id),
                source_system_id=str(source_system.id),
                snapshot_path=snapshot_path,
                raw_object_count=1,
                raw_record_count=len(raw_records),
            )
        except Exception as exc:
            ingestion_run.finished_at = datetime.now(timezone.utc)
            ingestion_run.status = IngestionStatus.FAILED
            ingestion_run.log_message = f"PhishTank ingestion failed: {exc}"
            await session.commit()
            raise

    async def _get_or_create_source_system(
        self, session: AsyncSession
    ) -> DataSourceSystem:
        source_system = await self.source_repository.get_by_name(
            session, self.source_name
        )
        if source_system is not None:
            return source_system

        return await self.source_service.create(
            session,
            DataSourceCreate(
                name=self.source_name,
                source_type=SourceType.API,
                description="Scheduled ingestion of the PhishTank online-valid feed",
                owner_name="PhishTank",
                legal_basis="public_threat_intel",
                contains_personal_data=False,
                retention_days=30,
            ),
        )

    async def _write_snapshot(
        self,
        *,
        ingestion_run: DataIngestionRun,
        entries: list[dict[str, Any]],
    ) -> tuple[Path, str, int]:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = self.snapshot_dir / f"phishtank_{ingestion_run.id}.json"
        snapshot_bytes = json.dumps(
            entries,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        snapshot_path.write_bytes(snapshot_bytes)
        return (
            snapshot_path,
            hashlib.sha256(snapshot_bytes).hexdigest(),
            len(snapshot_bytes),
        )

    def _build_raw_object(
        self,
        *,
        ingestion_run: DataIngestionRun,
        source_system: DataSourceSystem,
        snapshot_path: Path,
        content_hash: str,
        size_bytes: int,
        collected_at: datetime,
        entry_count: int,
    ) -> DataRawObject:
        storage_uri = self._to_storage_uri(snapshot_path)

        return DataRawObject(
            ingestion_run_id=ingestion_run.id,
            external_ref=f"{self.feed_client.feed_url}#run:{ingestion_run.id}",
            object_type=ObjectType.API_PAYLOAD,
            storage_uri=storage_uri,
            source_format="json",
            content_hash=content_hash,
            size_bytes=size_bytes,
            source_metadata={
                "feed_url": self.feed_client.feed_url,
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
    ) -> list[DataRawRecord]:
        extracted_at = datetime.now(timezone.utc)
        raw_records: list[DataRawRecord] = []

        for index, entry in enumerate(entries, start=1):
            url = self._clean_string(entry.get("url"))
            phish_id = self._clean_string(entry.get("phish_id"))
            record_key = phish_id or url or f"phishtank-row-{index}"
            raw_content = json.dumps(entry, ensure_ascii=False, sort_keys=True)
            is_usable = bool(url)
            rejection_reason = None if is_usable else "missing_url"

            raw_records.append(
                DataRawRecord(
                    raw_object_id=raw_object.id,
                    record_key=record_key,
                    raw_content=raw_content,
                    detected_language=None,
                    is_usable=is_usable,
                    rejection_reason=rejection_reason,
                    extracted_at=extracted_at,
                )
            )

        return raw_records

    @staticmethod
    def _clean_string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _to_storage_uri(snapshot_path: Path) -> str:
        try:
            return str(snapshot_path.relative_to(REPO_ROOT))
        except ValueError:
            return str(snapshot_path)
