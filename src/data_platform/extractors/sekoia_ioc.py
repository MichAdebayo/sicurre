"""SEKOIA.IO Community IOC ingestion.

The SEKOIA Community repository is public threat-intelligence material. Sicurre
ingests selected phishing/abuse-oriented IOC files as raw intelligence records
for the inference blocklist path, not as email-text training examples.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import ROOT_DIR, get_settings
from core.trace_logger import SemanticTraceLogger
from data_platform.api.schemas import DataSourceCreate, IngestionRunCreate
from data_platform.services.shared.snapshot_storage import (
    SnapshotStore,
    SnapshotWriteResult,
    build_snapshot_store,
)
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
from db.services.lineage import IngestionRunService, SourceSystemService

logger = logging.getLogger(__name__)

REPO_ROOT = ROOT_DIR
DEFAULT_SOURCE_NAME = "sekoia-community-ioc"
DEFAULT_SNAPSHOT_DIR = REPO_ROOT / "data" / "raw" / "scraping" / "sekoia_ioc"
DEFAULT_SNAPSHOT_PREFIX = "sekoia-community-ioc"
DEFAULT_GITHUB_API_ROOT = "https://api.github.com/repos/SEKOIA-IO/Community/git/trees/main"
DEFAULT_RAW_ROOT = "https://raw.githubusercontent.com/SEKOIA-IO/Community/main"
DEFAULT_ARCHIVE_URL = "https://codeload.github.com/SEKOIA-IO/Community/zip/refs/heads/main"

DEFAULT_TARGET_PATHS: tuple[str, ...] = (
    "sneaky2fa",
    "tycoon2fa",
    "global-analysis-aitm-phishing-threats",
    "clickfix_fake_google_meet",
    "clearfake",
    "fakebat",
)

CSV_EXTENSIONS = (".csv", ".txt")
IOC_FIELD_CANDIDATES = (
    "ioc",
    "ioc_value",
    "indicator",
    "value",
    "domain",
    "url",
    "ip",
)
DATE_FIELD_CANDIDATES = ("first seen", "valid from", "valid_from", "date")
VALID_UNTIL_FIELD_CANDIDATES = ("valid until", "valid_until", "expires")
DESCRIPTION_FIELD_CANDIDATES = ("description", "comment", "link", "source")

_DOMAIN_RE = re.compile(r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$")
_IPV4_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)
_HASH_RE = re.compile(r"^[a-fA-F0-9]{32,64}$")


@dataclass(frozen=True, slots=True)
class SekoiaIoc:
    value: str
    ioc_type: str
    campaign: str
    source_path: str
    first_seen: str | None = None
    valid_until: str | None = None
    description: str | None = None
    source_url: str | None = None


@dataclass(frozen=True, slots=True)
class SekoiaFetchedPayload:
    iocs: list[SekoiaIoc]
    snapshot_bytes: bytes
    content_type: str = "application/json"
    source_format: str = "json"
    source_url: str | None = "https://github.com/SEKOIA-IO/Community/tree/main/IOCs"


@dataclass(slots=True)
class SekoiaIocIngestionResult:
    ingestion_run_id: str
    source_system_id: str
    snapshot_path: Path | None
    snapshot_storage_uri: str
    raw_object_count: int
    raw_record_count: int
    skipped_count: int
    total_ioc_count: int
    log_message: str


class SekoiaCommunityClient:
    """Fetch selected SEKOIA Community IOC files through the GitHub API."""

    def __init__(
        self,
        *,
        api_root: str = DEFAULT_GITHUB_API_ROOT,
        target_paths: tuple[str, ...] = DEFAULT_TARGET_PATHS,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_root = api_root.rstrip("/")
        self.target_paths = target_paths
        self.timeout_seconds = timeout_seconds

    async def fetch_iocs(self) -> SekoiaFetchedPayload:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            try:
                files = await self._list_files(client)
                iocs = await self._fetch_listed_iocs(client, files)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in {403, 429}:
                    raise
                logger.warning("GitHub tree API rate-limited; using the public archive fallback.")
                iocs = await self._fetch_archive_iocs(client)

        unique_iocs = _dedupe_iocs(iocs)
        snapshot = {
            "source": "sekoia_ioc",
            "fetched_at": datetime.now(UTC).isoformat(),
            "target_paths": list(self.target_paths),
            "ioc_count": len(unique_iocs),
            "records": [ioc_to_payload(ioc) for ioc in unique_iocs],
        }
        return SekoiaFetchedPayload(
            iocs=unique_iocs,
            snapshot_bytes=json.dumps(
                snapshot, ensure_ascii=False, sort_keys=True, indent=2
            ).encode("utf-8"),
        )

    async def _fetch_listed_iocs(
        self,
        client: httpx.AsyncClient,
        files: list[dict[str, str]],
    ) -> list[SekoiaIoc]:
        """Fetch and parse files discovered through the GitHub tree API."""
        iocs: list[SekoiaIoc] = []
        for file_info in files:
            download_url = file_info.get("download_url")
            path = file_info.get("path", "")
            if not download_url:
                continue
            response = await client.get(download_url)
            response.raise_for_status()
            iocs.extend(
                parse_ioc_file(
                    response.text,
                    source_path=path,
                    source_url=download_url,
                )
            )
        return iocs

    async def _fetch_archive_iocs(self, client: httpx.AsyncClient) -> list[SekoiaIoc]:
        """Fetch selected files from GitHub's public archive after API throttling."""
        response = await client.get(DEFAULT_ARCHIVE_URL)
        response.raise_for_status()
        target_prefixes = tuple(
            f"Community-main/IOCs/{path.strip('/')}/" for path in self.target_paths
        )
        iocs: list[SekoiaIoc] = []
        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            for archive_path in archive.namelist():
                if not archive_path.startswith(target_prefixes):
                    continue
                if not archive_path.lower().endswith(CSV_EXTENSIONS):
                    continue
                source_path = archive_path.removeprefix("Community-main/")
                content = archive.read(archive_path).decode("utf-8-sig", errors="replace")
                iocs.extend(
                    parse_ioc_file(
                        content,
                        source_path=source_path,
                        source_url=f"{DEFAULT_ARCHIVE_URL}#{source_path}",
                    )
                )
        return iocs

    async def _list_files(self, client: httpx.AsyncClient) -> list[dict[str, str]]:
        """Discover selected IOC files with one bounded GitHub API request."""
        response = await client.get(f"{self.api_root}?recursive=1")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("truncated") is True:
            return []

        files: list[dict[str, str]] = []
        target_prefixes = tuple(f"IOCs/{path.strip('/')}/" for path in self.target_paths)
        for item in payload.get("tree", []):
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "")
            item_path = str(item.get("path") or "")
            if item_type != "blob" or not item_path.startswith(target_prefixes):
                continue
            if not item_path.lower().endswith(CSV_EXTENSIONS):
                continue
            files.append(
                {
                    "path": item_path,
                    "download_url": f"{DEFAULT_RAW_ROOT}/{quote(item_path, safe='/')}",
                }
            )
        return files


class SekoiaIocIngestionService:
    def __init__(
        self,
        *,
        client: SekoiaCommunityClient | None = None,
        fetch_iocs: Callable[[], Awaitable[SekoiaFetchedPayload]] | None = None,
        snapshot_dir: Path | None = None,
        snapshot_store: SnapshotStore | None = None,
        snapshot_prefix: str | None = None,
        source_name: str = DEFAULT_SOURCE_NAME,
    ) -> None:
        settings = get_settings()
        self.client = client or SekoiaCommunityClient()
        self.fetch_iocs = fetch_iocs or self.client.fetch_iocs
        self.snapshot_dir = snapshot_dir or DEFAULT_SNAPSHOT_DIR
        self.snapshot_prefix = snapshot_prefix or settings.sekoia_snapshot_prefix
        local_snapshot_root = (
            self.snapshot_dir.parent
            if self.snapshot_dir.name == self.snapshot_prefix
            else self.snapshot_dir
        )
        self.snapshot_store = snapshot_store or build_snapshot_store(
            local_root_dir=local_snapshot_root,
            repo_root=REPO_ROOT,
            source_key="sekoia",
        )
        self.source_name = source_name
        self.source_service = SourceSystemService()
        self.ingestion_service = IngestionRunService()
        self.source_repository = SourceSystemQueries()

    async def run(
        self,
        session: AsyncSession,
        *,
        trigger_mode: str = "scheduled",
        started_at: datetime | None = None,
    ) -> SekoiaIocIngestionResult:
        run_started_at = started_at or datetime.now(UTC)
        trace = SemanticTraceLogger(
            parent_type="Web Scraping",
            child_target="SEKOIA Community IOC",
            domain="data_platform",
        )
        trace.trace(
            stage="orchestration",
            status="start",
            message="SEKOIA Community IOC synchronization starting",
        )

        source_system = await self._get_or_create_source_system(session)
        ingestion_run = await self.ingestion_service.create(
            session,
            IngestionRunCreate(
                source_system_id=source_system.id,
                started_at=run_started_at,
                status=IngestionStatus.RUNNING,
                trigger_mode=trigger_mode,
                log_message="SEKOIA IOC ingestion started",
            ),
        )
        trace.set_trace_id(str(ingestion_run.id))

        try:
            payload = await self.fetch_iocs()
            await self._mark_existing_records_reference_only(session, source_system)
            existing_keys = await self._existing_record_keys(session)
            new_iocs = [ioc for ioc in payload.iocs if self._entry_key(ioc) not in existing_keys]
            skipped_count = len(payload.iocs) - len(new_iocs)

            if not new_iocs:
                ingestion_run.finished_at = datetime.now(UTC)
                ingestion_run.status = IngestionStatus.COMPLETED
                ingestion_run.log_message = (
                    f"SEKOIA IOC feed returned {len(payload.iocs)} IOC(s); "
                    "all were already ingested"
                )
                await session.commit()
                return self._empty_result(
                    ingestion_run,
                    source_system,
                    skipped_count=skipped_count,
                    total_ioc_count=len(payload.iocs),
                )

            snapshot_result = await self._write_snapshot(
                ingestion_run=ingestion_run,
                payload=payload,
            )
            raw_object = self._build_raw_object(
                ingestion_run=ingestion_run,
                source_system=source_system,
                snapshot_result=snapshot_result,
                collected_at=run_started_at,
                total_ioc_count=len(payload.iocs),
                new_ioc_count=len(new_iocs),
                source_url=payload.source_url,
                source_format=payload.source_format,
            )
            session.add(raw_object)
            await session.flush()

            raw_records = self._build_raw_records(
                raw_object=raw_object,
                iocs=new_iocs,
                source_system=source_system,
            )
            session.add_all(raw_records)

            log_message = (
                f"SEKOIA IOC ingestion completed: {len(raw_records)} new IOC(s), "
                f"{skipped_count} dedup-skipped."
            )
            ingestion_run.finished_at = datetime.now(UTC)
            ingestion_run.status = IngestionStatus.COMPLETED
            ingestion_run.raw_object_count = 1
            ingestion_run.raw_record_count = len(raw_records)
            ingestion_run.log_message = log_message
            await session.commit()

            trace.trace(
                stage="ingestion",
                status="success",
                message=log_message,
                metrics={"new_records": len(raw_records), "skipped": skipped_count},
            )
            return SekoiaIocIngestionResult(
                ingestion_run_id=str(ingestion_run.id),
                source_system_id=str(source_system.id),
                snapshot_path=snapshot_result.local_path,
                snapshot_storage_uri=snapshot_result.storage_uri,
                raw_object_count=1,
                raw_record_count=len(raw_records),
                skipped_count=skipped_count,
                total_ioc_count=len(payload.iocs),
                log_message=log_message,
            )
        except Exception as exc:
            ingestion_run.finished_at = datetime.now(UTC)
            ingestion_run.status = IngestionStatus.FAILED
            ingestion_run.log_message = f"SEKOIA IOC ingestion failed: {exc}"
            await session.commit()
            trace.trace(
                stage="ingestion",
                status="failed",
                message=f"SEKOIA IOC ingestion failed: {exc}",
            )
            raise

    def _empty_result(
        self,
        run: DataIngestionRun,
        source: DataSourceSystem,
        *,
        skipped_count: int,
        total_ioc_count: int,
    ) -> SekoiaIocIngestionResult:
        return SekoiaIocIngestionResult(
            ingestion_run_id=str(run.id),
            source_system_id=str(source.id),
            snapshot_path=None,
            snapshot_storage_uri="",
            raw_object_count=0,
            raw_record_count=0,
            skipped_count=skipped_count,
            total_ioc_count=total_ioc_count,
            log_message=run.log_message or "",
        )

    async def _existing_record_keys(self, session: AsyncSession) -> set[str]:
        stmt = (
            select(DataRawRecord.record_key)
            .join(DataRawObject)
            .join(DataIngestionRun)
            .join(DataSourceSystem)
            .where(DataSourceSystem.name == self.source_name)
        )
        rows = await session.scalars(stmt)
        return set(rows)

    async def _mark_existing_records_reference_only(
        self,
        session: AsyncSession,
        source_system: DataSourceSystem,
    ) -> None:
        """Repair legacy SEKOIA rows before applying incremental deduplication."""
        await session.execute(
            update(DataRawRecord)
            .where(DataRawRecord.source_system_id == source_system.id)
            .values(
                is_usable=False,
                rejection_reason="ioc_reference_only_not_email_training_text",
            )
        )

    async def _get_or_create_source_system(self, session: AsyncSession) -> DataSourceSystem:
        source_system = await self.source_repository.get_by_name(session, self.source_name)
        if source_system is not None:
            return source_system

        return await self.source_service.create(
            session,
            DataSourceCreate(
                name=self.source_name,
                source_type=SourceType.SCRAPING,
                description=(
                    "Scheduled ingestion of public SEKOIA.IO Community phishing "
                    "and abuse indicators of compromise"
                ),
                owner_name="SEKOIA.IO",
                legal_basis="public_threat_intel",
                contains_personal_data=False,
                retention_days=180,
            ),
        )

    async def _write_snapshot(
        self,
        *,
        ingestion_run: DataIngestionRun,
        payload: SekoiaFetchedPayload,
    ) -> SnapshotWriteResult:
        object_key = self._build_snapshot_object_key(ingestion_run)
        return await self.snapshot_store.write_snapshot(
            object_key=object_key,
            payload=payload.snapshot_bytes,
            content_type=payload.content_type,
        )

    def _build_raw_object(
        self,
        *,
        ingestion_run: DataIngestionRun,
        source_system: DataSourceSystem,
        snapshot_result: SnapshotWriteResult,
        collected_at: datetime,
        total_ioc_count: int,
        new_ioc_count: int,
        source_url: str | None,
        source_format: str,
    ) -> DataRawObject:
        return DataRawObject(
            ingestion_run_id=ingestion_run.id,
            external_ref=source_url or f"sekoia-community#run:{ingestion_run.id}",
            object_type=ObjectType.API_PAYLOAD,
            storage_uri=snapshot_result.storage_uri,
            source_format=source_format,
            content_hash=snapshot_result.content_hash,
            size_bytes=snapshot_result.size_bytes,
            source_metadata={
                "source_name": source_system.name,
                "source": "sekoia_ioc",
                "total_ioc_count": total_ioc_count,
                "new_ioc_count": new_ioc_count,
            },
            collected_at=collected_at,
        )

    def _build_raw_records(
        self,
        *,
        raw_object: DataRawObject,
        iocs: list[SekoiaIoc],
        source_system: DataSourceSystem,
    ) -> list[DataRawRecord]:
        extracted_at = datetime.now(UTC)
        return [
            DataRawRecord(
                raw_object_id=raw_object.id,
                source_system_id=source_system.id,
                record_key=self._entry_key(ioc),
                raw_content=json.dumps(ioc_to_payload(ioc), ensure_ascii=False, sort_keys=True),
                detected_language=None,
                is_usable=False,
                rejection_reason="ioc_reference_only_not_email_training_text",
                extracted_at=extracted_at,
            )
            for ioc in iocs
        ]

    @staticmethod
    def _entry_key(ioc: SekoiaIoc) -> str:
        raw_key = f"{ioc.ioc_type}:{ioc.value.lower()}:{ioc.campaign.lower()}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def _build_snapshot_object_key(self, ingestion_run: DataIngestionRun) -> str:
        date_str = ingestion_run.started_at.strftime("%Y%m%d")
        filename = f"sekoia_ioc_{date_str}_{ingestion_run.id}.json"
        return self.snapshot_store.build_object_key(
            source_prefix=self.snapshot_prefix,
            filename=filename,
        )


def parse_ioc_file(
    content: str,
    *,
    source_path: str,
    source_url: str | None = None,
) -> list[SekoiaIoc]:
    if source_path.lower().endswith(".csv"):
        return _parse_csv_iocs(content, source_path=source_path, source_url=source_url)
    return _parse_text_iocs(content, source_path=source_path, source_url=source_url)


def _parse_csv_iocs(
    content: str,
    *,
    source_path: str,
    source_url: str | None,
) -> list[SekoiaIoc]:
    rows = csv.DictReader(StringIO(content))
    iocs: list[SekoiaIoc] = []
    for row in rows:
        normalized_row = {_normalize_field_name(k): v for k, v in row.items() if k}
        value = _first_present(normalized_row, IOC_FIELD_CANDIDATES)
        if not value:
            continue
        parsed = _build_ioc(
            value=value,
            source_path=source_path,
            source_url=source_url,
            first_seen=_first_present(normalized_row, DATE_FIELD_CANDIDATES),
            valid_until=_first_present(normalized_row, VALID_UNTIL_FIELD_CANDIDATES),
            description=_first_present(normalized_row, DESCRIPTION_FIELD_CANDIDATES),
        )
        if parsed is not None:
            iocs.append(parsed)
    return iocs


def _parse_text_iocs(
    content: str,
    *,
    source_path: str,
    source_url: str | None,
) -> list[SekoiaIoc]:
    iocs: list[SekoiaIoc] = []
    for line in content.splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        parsed = _build_ioc(
            value=value,
            source_path=source_path,
            source_url=source_url,
            description="SEKOIA Community text IOC",
        )
        if parsed is not None:
            iocs.append(parsed)
    return iocs


def _build_ioc(
    *,
    value: str,
    source_path: str,
    source_url: str | None,
    first_seen: str | None = None,
    valid_until: str | None = None,
    description: str | None = None,
) -> SekoiaIoc | None:
    cleaned = value.strip().strip('"').strip("'")
    if not cleaned:
        return None
    ioc_type, canonical_value = classify_ioc(cleaned)
    if ioc_type == "unknown":
        return None
    return SekoiaIoc(
        value=canonical_value,
        ioc_type=ioc_type,
        campaign=_campaign_from_path(source_path),
        source_path=source_path,
        first_seen=_clean_optional(first_seen),
        valid_until=_clean_optional(valid_until),
        description=_clean_optional(description),
        source_url=source_url,
    )


def classify_ioc(value: str) -> tuple[str, str]:
    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = parsed.hostname or ""
    if value.startswith(("http://", "https://")) and host:
        return "url", value.strip()
    if _IPV4_RE.match(value):
        return "ipv4", value
    if _HASH_RE.match(value):
        return "hash", value.lower()
    if _DOMAIN_RE.match(value):
        return "domain", value.lower().lstrip(".")
    if host and _DOMAIN_RE.match(host):
        return "domain", host.lower().lstrip(".")
    return "unknown", value


def ioc_to_payload(ioc: SekoiaIoc) -> dict[str, Any]:
    return {
        "source": "sekoia_ioc",
        "label": "phishing",
        "ioc": ioc.value,
        "ioc_type": ioc.ioc_type,
        "campaign": ioc.campaign,
        "source_path": ioc.source_path,
        "source_url": ioc.source_url,
        "first_seen": ioc.first_seen,
        "valid_until": ioc.valid_until,
        "description": ioc.description,
    }


def _dedupe_iocs(iocs: list[SekoiaIoc]) -> list[SekoiaIoc]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[SekoiaIoc] = []
    for ioc in iocs:
        key = (ioc.ioc_type, ioc.value.lower(), ioc.campaign.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ioc)
    return deduped


def _campaign_from_path(source_path: str) -> str:
    parts = [part for part in source_path.split("/") if part and part != "IOCs"]
    if len(parts) >= 2 and parts[0] == "global-analysis-aitm-phishing-threats":
        return parts[1]
    return parts[0] if parts else "sekoia-community"


def _normalize_field_name(value: str) -> str:
    return value.strip().lower().replace("_", " ")


def _first_present(row: dict[str, str | None], candidates: tuple[str, ...]) -> str | None:
    normalized_candidates = {_normalize_field_name(candidate) for candidate in candidates}
    for key, value in row.items():
        if key in normalized_candidates and value and str(value).strip():
            return str(value).strip()
    return None


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
