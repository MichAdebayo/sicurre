from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import feedparser
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
from sicurre_api.domains.data_platform.services.snapshot_storage import (
    SnapshotStore,
    SnapshotWriteResult,
    build_snapshot_store,
)


REPO_ROOT = BACKEND_ROOT.parent
DEFAULT_CERTFR_SOURCE_NAME = "cert-fr-cti"
DEFAULT_CERTFR_SNAPSHOT_DIR = REPO_ROOT / "data" / "raw" / "scraping" / "cert_fr"
DEFAULT_CERTFR_SNAPSHOT_PREFIX = "cert-fr"
CERTFR_REFERENCE_PATTERN = re.compile(r"(CERTFR-\d{4}-[A-Z]{3}-\d+)", re.IGNORECASE)
DEFAULT_CERTFR_FEEDS: tuple[tuple[str, str], ...] = (
    ("actualite", "https://www.cert.ssi.gouv.fr/actualite/feed/"),
    ("alerte", "https://www.cert.ssi.gouv.fr/alerte/feed/"),
    ("avis", "https://www.cert.ssi.gouv.fr/avis/feed/"),
    ("cti", "https://www.cert.ssi.gouv.fr/cti/feed/"),
)


@dataclass(frozen=True, slots=True)
class CertFRFeed:
    name: str
    url: str


@dataclass(slots=True)
class CertFRIngestionResult:
    ingestion_run_id: str
    source_system_id: str
    snapshot_path: Path | None
    snapshot_storage_uri: str
    raw_object_count: int
    raw_record_count: int


class CertFRFeedClient:
    def __init__(
        self,
        *,
        feeds: Sequence[CertFRFeed] | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.feeds = tuple(feeds or self._default_feeds())
        self.timeout_seconds = timeout_seconds

    async def fetch_entries(self) -> dict[str, list[dict[str, Any]]]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            payloads: dict[str, list[dict[str, Any]]] = {}
            for feed in self.feeds:
                response = await client.get(feed.url)
                response.raise_for_status()
                payloads[feed.name] = await asyncio.to_thread(
                    self._parse_feed_payload,
                    feed.name,
                    response.content,
                )
        return payloads

    @staticmethod
    def _default_feeds() -> tuple[CertFRFeed, ...]:
        return tuple(
            CertFRFeed(name=name, url=url) for name, url in DEFAULT_CERTFR_FEEDS
        )

    @staticmethod
    def _parse_feed_payload(
        feed_name: str,
        payload: bytes,
    ) -> list[dict[str, Any]]:
        parsed = feedparser.parse(payload)
        if getattr(parsed, "bozo", False) and not parsed.entries:
            raise ValueError(f"CERT-FR feed '{feed_name}' returned invalid RSS")

        entries: list[dict[str, Any]] = []
        for entry in parsed.entries:
            title = CertFRFeedClient._clean_string(entry.get("title"))
            link = CertFRFeedClient._clean_string(entry.get("link"))
            guid = CertFRFeedClient._clean_string(entry.get("id"))
            summary = CertFRFeedClient._clean_string(entry.get("summary"))
            reference = CertFRFeedClient._extract_reference(guid, link, title)
            categories = [
                term
                for tag in entry.get("tags", [])
                if (term := CertFRFeedClient._clean_string(tag.get("term")))
            ]

            entries.append(
                {
                    "title": title,
                    "link": link,
                    "guid": guid,
                    "summary": summary,
                    "published": CertFRFeedClient._clean_string(entry.get("published")),
                    "updated": CertFRFeedClient._clean_string(
                        entry.get("updated") if "updated" in entry else None
                    ),
                    "reference": reference,
                    "categories": categories,
                }
            )

        return entries

    @staticmethod
    def _extract_reference(*candidates: str | None) -> str | None:
        for candidate in candidates:
            if candidate is None:
                continue
            match = CERTFR_REFERENCE_PATTERN.search(candidate)
            if match is not None:
                return match.group(1).upper()
        return None

    @staticmethod
    def _clean_string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class CertFRIngestionService:
    def __init__(
        self,
        *,
        feed_client: CertFRFeedClient | None = None,
        fetch_entries: (
            Callable[[], Awaitable[dict[str, list[dict[str, Any]]]]] | None
        ) = None,
        snapshot_dir: Path = DEFAULT_CERTFR_SNAPSHOT_DIR,
        snapshot_store: SnapshotStore | None = None,
        snapshot_prefix: str = DEFAULT_CERTFR_SNAPSHOT_PREFIX,
        source_name: str = DEFAULT_CERTFR_SOURCE_NAME,
    ) -> None:
        self.feed_client = feed_client or CertFRFeedClient()
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
    ) -> CertFRIngestionResult:
        run_started_at = started_at or datetime.now(timezone.utc)
        source_system = await self._get_or_create_source_system(session)
        ingestion_run = await self.ingestion_service.create(
            session,
            IngestionRunCreate(
                source_system_id=source_system.id,
                started_at=run_started_at,
                status=IngestionStatus.RUNNING,
                trigger_mode=trigger_mode,
                log_message="CERT-FR ingestion started",
            ),
        )

        try:
            feed_entries = await self.fetch_entries()
            normalized_entries = self._normalize_feed_entries(feed_entries)
            snapshot_result = await self._write_snapshot(
                ingestion_run=ingestion_run,
                entries_by_feed=normalized_entries,
            )
            raw_object = self._build_raw_object(
                ingestion_run=ingestion_run,
                source_system=source_system,
                snapshot_result=snapshot_result,
                collected_at=run_started_at,
                entries_by_feed=normalized_entries,
            )
            session.add(raw_object)
            await session.flush()

            raw_records = self._build_raw_records(
                raw_object=raw_object,
                entries_by_feed=normalized_entries,
            )
            session.add_all(raw_records)

            ingestion_run.finished_at = datetime.now(timezone.utc)
            ingestion_run.status = IngestionStatus.COMPLETED
            ingestion_run.raw_object_count = 1
            ingestion_run.raw_record_count = len(raw_records)
            ingestion_run.log_message = (
                f"CERT-FR ingestion completed with {len(raw_records)} records"
            )
            await session.commit()

            return CertFRIngestionResult(
                ingestion_run_id=str(ingestion_run.id),
                source_system_id=str(source_system.id),
                snapshot_path=snapshot_result.local_path,
                snapshot_storage_uri=snapshot_result.storage_uri,
                raw_object_count=1,
                raw_record_count=len(raw_records),
            )
        except Exception as exc:
            ingestion_run.finished_at = datetime.now(timezone.utc)
            ingestion_run.status = IngestionStatus.FAILED
            ingestion_run.log_message = f"CERT-FR ingestion failed: {exc}"
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
                source_type=SourceType.SCRAPING,
                description="Scheduled ingestion of CERT-FR RSS feeds",
                owner_name="ANSSI",
                legal_basis="public_threat_intel",
                contains_personal_data=False,
                retention_days=30,
            ),
        )

    def _normalize_feed_entries(
        self,
        feed_entries: Mapping[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        normalized: dict[str, list[dict[str, Any]]] = {}
        for feed_name, entries in feed_entries.items():
            normalized[feed_name] = []
            for entry in entries:
                entry_with_feed = dict(entry)
                entry_with_feed["feed_name"] = feed_name
                normalized[feed_name].append(entry_with_feed)
        return normalized

    async def _write_snapshot(
        self,
        *,
        ingestion_run: DataIngestionRun,
        entries_by_feed: Mapping[str, list[dict[str, Any]]],
    ) -> SnapshotWriteResult:
        snapshot_bytes = json.dumps(
            entries_by_feed,
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
        entries_by_feed: Mapping[str, list[dict[str, Any]]],
    ) -> DataRawObject:
        feed_counts = {
            feed_name: len(entries) for feed_name, entries in entries_by_feed.items()
        }
        feed_urls = {feed.name: feed.url for feed in self.feed_client.feeds}
        return DataRawObject(
            ingestion_run_id=ingestion_run.id,
            external_ref=f"cert-fr#rss#run:{ingestion_run.id}",
            object_type=ObjectType.API_PAYLOAD,
            storage_uri=snapshot_result.storage_uri,
            source_format="json",
            content_hash=snapshot_result.content_hash,
            size_bytes=snapshot_result.size_bytes,
            source_metadata={
                "source_name": source_system.name,
                "feed_counts": feed_counts,
                "feed_urls": feed_urls,
                "source_feed_format": "rss",
            },
            collected_at=collected_at,
        )

    def _build_raw_records(
        self,
        *,
        raw_object: DataRawObject,
        entries_by_feed: Mapping[str, list[dict[str, Any]]],
    ) -> list[DataRawRecord]:
        extracted_at = datetime.now(timezone.utc)
        raw_records: list[DataRawRecord] = []

        for feed_name, entries in entries_by_feed.items():
            for index, entry in enumerate(entries, start=1):
                link = self._clean_string(entry.get("link"))
                guid = self._clean_string(entry.get("guid"))
                title = self._clean_string(entry.get("title"))
                reference = self._clean_string(
                    entry.get("reference")
                ) or CertFRFeedClient._extract_reference(
                    guid,
                    link,
                    title,
                )
                record_key = reference or guid or link or f"{feed_name}-row-{index}"
                raw_content = json.dumps(entry, ensure_ascii=False, sort_keys=True)
                is_usable = bool(title and (guid or link))
                rejection_reason = None if is_usable else "missing_title_or_locator"

                raw_records.append(
                    DataRawRecord(
                        raw_object_id=raw_object.id,
                        record_key=record_key,
                        raw_content=raw_content,
                        detected_language=self._detect_language(entry),
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

    def _detect_language(self, entry: Mapping[str, Any]) -> str | None:
        title = self._clean_string(entry.get("title")) or ""
        summary = self._clean_string(entry.get("summary")) or ""
        combined_text = f"{title} {summary}".strip()
        if not combined_text:
            return None
        lowered_text = combined_text.lower()
        if "english version" in lowered_text or "version française" in lowered_text:
            return "en"
        if "🇬🇧" in combined_text:
            return "en"
        return "fr"

    def _build_snapshot_object_key(self, ingestion_run: DataIngestionRun) -> str:
        filename = f"certfr_{ingestion_run.id}.json"
        return self.snapshot_store.build_object_key(
            source_prefix=self.snapshot_prefix,
            filename=filename,
        )
