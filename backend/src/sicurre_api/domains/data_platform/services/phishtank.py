from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sicurre_api.core.config import BACKEND_ROOT, get_settings
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
from sicurre_api.domains.data_platform.services.snapshot_storage import (
    SnapshotStore,
    SnapshotWriteResult,
    build_snapshot_store,
)

logger = logging.getLogger(__name__)

REPO_ROOT = BACKEND_ROOT.parent
DEFAULT_PHISHTANK_FEED_URL = "https://data.phishtank.com/data/online-valid.json"
DEFAULT_PHISHTANK_SOURCE_NAME = "phishtank-online-valid"
DEFAULT_PHISHTANK_SNAPSHOT_DIR = REPO_ROOT / "data" / "raw" / "api" / "phishtank"
DEFAULT_PHISHTANK_SNAPSHOT_PREFIX = "phishtank"

# Retry config for PhishTank 509 (rate limit) responses
MAX_RETRIES = 3
RETRY_BACKOFF_BASE_SECONDS = 30.0
RETRY_STATUS_CODES: frozenset[int] = frozenset((429, 503, 509))


@dataclass(slots=True)
class PhishTankIngestionResult:
    ingestion_run_id: str
    source_system_id: str
    snapshot_path: Path | None
    snapshot_storage_uri: str
    raw_object_count: int
    raw_record_count: int
    skipped_count: int
    log_message: str


class PhishTankFeedClient:
    def __init__(
        self,
        *,
        feed_url: str = DEFAULT_PHISHTANK_FEED_URL,
        api_key: str | None = None,
        timeout_seconds: float = 120.0,
        max_retries: int = MAX_RETRIES,
        retry_backoff_seconds: float = RETRY_BACKOFF_BASE_SECONDS,
    ) -> None:
        self._base_feed_url = feed_url
        self._api_key = api_key
        self.feed_url = self._build_feed_url(feed_url, api_key)
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds

    @staticmethod
    def _build_feed_url(base_url: str, api_key: str | None) -> str:
        """Insert API key into feed URL if available.

        PhishTank URL pattern with key:
            ``https://data.phishtank.com/data/{API_KEY}/online-valid.json``
        Without key:
            ``https://data.phishtank.com/data/online-valid.json``
        """
        if not api_key:
            return base_url
        # Insert key before the filename segment
        parts = base_url.rsplit("/", 1)
        if len(parts) == 2:
            return f"{parts[0]}/{api_key}/{parts[1]}"
        return base_url

    async def fetch_entries(self) -> list[dict[str, Any]]:
        """Fetch feed with retry logic for rate-limit errors."""
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds,
                ) as client:
                    response = await client.get(self.feed_url)

                    if response.status_code in RETRY_STATUS_CODES:
                        wait = self.retry_backoff_seconds * (2 ** attempt)
                        logger.warning(
                            "PhishTank returned %d (attempt %d/%d), "
                            "retrying in %.0fs",
                            response.status_code,
                            attempt + 1,
                            self.max_retries + 1,
                            wait,
                        )
                        if attempt < self.max_retries:
                            await asyncio.sleep(wait)
                            continue
                        response.raise_for_status()

                    response.raise_for_status()
                    payload = response.json()

                if not isinstance(payload, list):
                    raise ValueError("PhishTank feed must return a JSON array")

                return [
                    entry for entry in payload if isinstance(entry, dict)
                ]

            except httpx.RequestError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    wait = self.retry_backoff_seconds * (2 ** attempt)
                    logger.warning(
                        "PhishTank request failed (attempt %d/%d): %s, "
                        "retrying in %.0fs",
                        attempt + 1,
                        self.max_retries + 1,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    continue

        raise last_error or RuntimeError("PhishTank fetch failed after retries")


class PhishTankIngestionService:
    def __init__(
        self,
        *,
        feed_client: PhishTankFeedClient | None = None,
        fetch_entries: (
            Callable[[], Awaitable[list[dict[str, Any]]]] | None
        ) = None,
        snapshot_dir: Path = DEFAULT_PHISHTANK_SNAPSHOT_DIR,
        snapshot_store: SnapshotStore | None = None,
        snapshot_prefix: str = DEFAULT_PHISHTANK_SNAPSHOT_PREFIX,
        source_name: str = DEFAULT_PHISHTANK_SOURCE_NAME,
    ) -> None:
        settings = get_settings()

        # Build feed client with API key from settings if available
        api_key = getattr(settings, "phishtank_api_key", None)
        self.feed_client = feed_client or PhishTankFeedClient(
            api_key=api_key,
        )
        self.fetch_entries = fetch_entries or self.feed_client.fetch_entries
        self.snapshot_dir = snapshot_dir
        self.snapshot_prefix = snapshot_prefix
        local_snapshot_root = (
            snapshot_dir.parent
            if snapshot_dir.name == snapshot_prefix
            else snapshot_dir
        )
        self.snapshot_store = snapshot_store or build_snapshot_store(
            local_root_dir=local_snapshot_root,
            repo_root=REPO_ROOT,
        )
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

            if not entries:
                ingestion_run.finished_at = datetime.now(timezone.utc)
                ingestion_run.status = IngestionStatus.COMPLETED
                ingestion_run.log_message = (
                    "PhishTank feed returned 0 entries — nothing to ingest"
                )
                await session.commit()
                return PhishTankIngestionResult(
                    ingestion_run_id=str(ingestion_run.id),
                    source_system_id=str(source_system.id),
                    snapshot_path=None,
                    snapshot_storage_uri="",
                    raw_object_count=0,
                    raw_record_count=0,
                    skipped_count=0,
                    log_message=ingestion_run.log_message,
                )

            # ---------- Dedup: skip already-ingested phish_ids ----------
            existing_keys = await self._existing_record_keys(session)
            new_entries = [
                e for e in entries
                if self._entry_key(e) not in existing_keys
            ]
            skipped_count = len(entries) - len(new_entries)

            if not new_entries:
                ingestion_run.finished_at = datetime.now(timezone.utc)
                ingestion_run.status = IngestionStatus.COMPLETED
                ingestion_run.log_message = (
                    f"All {len(entries)} PhishTank entries already ingested "
                    f"— nothing new"
                )
                await session.commit()
                return PhishTankIngestionResult(
                    ingestion_run_id=str(ingestion_run.id),
                    source_system_id=str(source_system.id),
                    snapshot_path=None,
                    snapshot_storage_uri="",
                    raw_object_count=0,
                    raw_record_count=0,
                    skipped_count=skipped_count,
                    log_message=ingestion_run.log_message,
                )

            # ---------- Snapshot only new entries ----------
            snapshot_result = await self._write_snapshot(
                ingestion_run=ingestion_run,
                entries=new_entries,
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
                raw_object=raw_object, entries=new_entries
            )
            session.add_all(raw_records)

            log_message = (
                f"PhishTank ingestion completed: "
                f"{len(raw_records)} new, {skipped_count} skipped"
            )
            ingestion_run.finished_at = datetime.now(timezone.utc)
            ingestion_run.status = IngestionStatus.COMPLETED
            ingestion_run.raw_object_count = 1
            ingestion_run.raw_record_count = len(raw_records)
            ingestion_run.log_message = log_message
            await session.commit()

            return PhishTankIngestionResult(
                ingestion_run_id=str(ingestion_run.id),
                source_system_id=str(source_system.id),
                snapshot_path=snapshot_result.local_path,
                snapshot_storage_uri=snapshot_result.storage_uri,
                raw_object_count=1,
                raw_record_count=len(raw_records),
                skipped_count=skipped_count,
                log_message=log_message,
            )
        except Exception as exc:
            ingestion_run.finished_at = datetime.now(timezone.utc)
            ingestion_run.status = IngestionStatus.FAILED
            ingestion_run.log_message = f"PhishTank ingestion failed: {exc}"
            await session.commit()
            raise

    # ------------------------------------------------------------------
    # Dedup helpers
    # ------------------------------------------------------------------

    async def _existing_record_keys(
        self, session: AsyncSession,
    ) -> set[str]:
        """Return record keys already stored from PhishTank ingestion runs.

        Queries ``DataRawRecord.record_key`` for records linked to
        ``DataRawObject``s belonging to this source system.
        """
        stmt = (
            select(DataRawRecord.record_key)
            .join(DataRawObject)
            .join(DataIngestionRun)
            .join(DataSourceSystem)
            .where(DataSourceSystem.name == self.source_name)
        )
        rows = await session.scalars(stmt)
        return set(rows)

    @staticmethod
    def _entry_key(entry: dict[str, Any]) -> str:
        phish_id = entry.get("phish_id")
        if phish_id is not None:
            return str(phish_id).strip()
        url = entry.get("url")
        if url is not None:
            return str(url).strip()
        return ""

    # ------------------------------------------------------------------
    # Source system
    # ------------------------------------------------------------------

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
                description=(
                    "Scheduled ingestion of the PhishTank online-valid feed"
                ),
                owner_name="PhishTank",
                legal_basis="public_threat_intel",
                contains_personal_data=False,
                retention_days=30,
            ),
        )

    # ------------------------------------------------------------------
    # Snapshot & records
    # ------------------------------------------------------------------

    async def _write_snapshot(
        self,
        *,
        ingestion_run: DataIngestionRun,
        entries: list[dict[str, Any]],
    ) -> SnapshotWriteResult:
        snapshot_bytes = json.dumps(
            entries,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        object_key = self._build_snapshot_object_key(ingestion_run)
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
            external_ref=(
                f"{self.feed_client._base_feed_url}#run:{ingestion_run.id}"
            ),
            object_type=ObjectType.API_PAYLOAD,
            storage_uri=snapshot_result.storage_uri,
            source_format="json",
            content_hash=snapshot_result.content_hash,
            size_bytes=snapshot_result.size_bytes,
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
            raw_content = json.dumps(
                entry, ensure_ascii=False, sort_keys=True,
            )
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

    def _build_snapshot_object_key(
        self, ingestion_run: DataIngestionRun,
    ) -> str:
        filename = f"phishtank_{ingestion_run.id}.json"
        return self.snapshot_store.build_object_key(
            source_prefix=self.snapshot_prefix,
            filename=filename,
        )
