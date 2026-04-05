from __future__ import annotations

import asyncio
import csv
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import ROOT_DIR, get_settings
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
DEFAULT_PHISHTANK_FEED_URL = "https://data.phishtank.com/data/online-valid.csv"
DEFAULT_PHISHTANK_SOURCE_NAME = "phishtank-online-valid"
DEFAULT_PHISHTANK_SNAPSHOT_DIR = REPO_ROOT / "data" / "raw" / "api" / "phishtank"
DEFAULT_PHISHTANK_SNAPSHOT_PREFIX = "phishtank"

# Retry config for PhishTank 509 (rate limit) responses
MAX_RETRIES = 3
RETRY_BACKOFF_BASE_SECONDS = 30.0
RETRY_STATUS_CODES: frozenset[int] = frozenset((429, 503, 509))

# ── French filtering (from notebook 05_phishtank_extraction) ─────────
FR_TLD_PATTERN: re.Pattern[str] = re.compile(r"\.fr(/|$|:)", re.IGNORECASE)

FR_BRAND_KEYWORDS: tuple[str, ...] = (
    # Government / health
    "urssaf", "ameli", "impots", "dgfip", "caf", "cpam",
    "securite-sociale", "france-connect", "franceconnect",
    "service-public", "gouv",
    # Postal / delivery
    "laposte", "la-poste", "colissimo", "chronopost", "mondial-relay",
    # Banking
    "credit-agricole", "creditagricole", "bnp", "bnpparibas",
    "banque-postale", "banquepostale", "societe-generale",
    "societegenerale", "lcl", "caisse-epargne", "credit-mutuel",
    # Telecom
    "orange", "sfr", "bouygues", "free",
    # E-commerce
    "leboncoin", "cdiscount", "fnac",
)


@dataclass(slots=True)
class PhishTankIngestionResult:
    ingestion_run_id: str
    source_system_id: str
    snapshot_path: Path | None
    snapshot_storage_uri: str
    raw_object_count: int
    raw_record_count: int
    skipped_count: int
    filtered_count: int
    total_feed_count: int
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
            ``https://data.phishtank.com/data/{API_KEY}/online-valid.csv``
        Without key:
            ``https://data.phishtank.com/data/online-valid.csv``
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
        settings = get_settings()

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(
                        self.feed_url,
                        headers={"User-Agent": settings.phishtank_user_agent},
                    )

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
                    # Parse CSV payload
                    text = response.text
                    reader = csv.DictReader(text.splitlines())
                    return [
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
        self.source_repository = SourceSystemQueries()

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
            all_entries = await self.fetch_entries()
            total_feed_count = len(all_entries)

            if not all_entries:
                ingestion_run.finished_at = datetime.now(timezone.utc)
                ingestion_run.status = IngestionStatus.COMPLETED
                ingestion_run.log_message = (
                    "PhishTank feed returned 0 entries — nothing to ingest"
                )
                await session.commit()
                return self._empty_result(
                    ingestion_run, source_system,
                    total_feed_count=0,
                )

            # ---- Step 1: French-targeted filter ----
            entries = [
                e for e in all_entries
                if self._is_french_target(e.get("url", ""))
            ]
            filtered_count = total_feed_count - len(entries)

            if not entries:
                ingestion_run.finished_at = datetime.now(timezone.utc)
                ingestion_run.status = IngestionStatus.COMPLETED
                ingestion_run.log_message = (
                    f"PhishTank feed had {total_feed_count} entries but "
                    f"0 matched French filters — nothing to ingest"
                )
                await session.commit()
                return self._empty_result(
                    ingestion_run, source_system,
                    filtered_count=filtered_count,
                    total_feed_count=total_feed_count,
                )

            # ---- Step 2: Dedup against existing DB records ----
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
                    f"All {len(entries)} French PhishTank entries already "
                    f"ingested — nothing new (feed={total_feed_count})"
                )
                await session.commit()
                return self._empty_result(
                    ingestion_run, source_system,
                    skipped_count=skipped_count,
                    filtered_count=filtered_count,
                    total_feed_count=total_feed_count,
                )

            # ---- Step 3: Snapshot + DB write ----
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
                raw_object=raw_object, entries=new_entries,
            )
            session.add_all(raw_records)

            log_message = (
                f"PhishTank ingestion completed: "
                f"{len(raw_records)} new French entries, "
                f"{skipped_count} dedup-skipped, "
                f"{filtered_count} non-French filtered "
                f"(feed={total_feed_count})"
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
                filtered_count=filtered_count,
                total_feed_count=total_feed_count,
                log_message=log_message,
            )
        except Exception as exc:
            ingestion_run.finished_at = datetime.now(timezone.utc)
            ingestion_run.status = IngestionStatus.FAILED
            ingestion_run.log_message = f"PhishTank ingestion failed: {exc}"
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
        filtered_count: int = 0,
        total_feed_count: int = 0,
    ) -> PhishTankIngestionResult:
        return PhishTankIngestionResult(
            ingestion_run_id=str(run.id),
            source_system_id=str(source.id),
            snapshot_path=None,
            snapshot_storage_uri="",
            raw_object_count=0,
            raw_record_count=0,
            skipped_count=skipped_count,
            filtered_count=filtered_count,
            total_feed_count=total_feed_count,
            log_message=run.log_message or "",
        )

    # ------------------------------------------------------------------
    # French filtering (from notebook 05)
    # ------------------------------------------------------------------

    @staticmethod
    def _is_french_target(url: str) -> bool:
        """Return ``True`` if *url* targets French users.

        Checks ``.fr`` TLD and 34 French brand keywords.
        """
        url_lower = url.lower()
        if FR_TLD_PATTERN.search(url_lower):
            return True
        return any(kw in url_lower for kw in FR_BRAND_KEYWORDS)

    @staticmethod
    def _parse_domain(url: str) -> str:
        """Extract the network location (domain) from a URL."""
        try:
            return urlparse(url).netloc or ""
        except Exception:
            return ""

    @staticmethod
    def _french_filter_reason(url: str) -> str:
        """Return why a URL matched the French filter."""
        url_lower = url.lower()
        if FR_TLD_PATTERN.search(url_lower):
            return "fr_tld"
        for kw in FR_BRAND_KEYWORDS:
            if kw in url_lower:
                return f"brand:{kw}"
        return ""

    # ------------------------------------------------------------------
    # Dedup helpers
    # ------------------------------------------------------------------

    async def _existing_record_keys(
        self, session: AsyncSession,
    ) -> set[str]:
        """Return record keys already stored from PhishTank ingestion runs."""
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

            # Enrich with domain + filter reason before storing
            enriched = dict(entry)
            if url:
                enriched["domain"] = self._parse_domain(url)
                enriched["filter_reason"] = self._french_filter_reason(url)
            enriched["label"] = "phishing"
            enriched["source"] = "phishtank_api"

            raw_content = json.dumps(
                enriched, ensure_ascii=False, sort_keys=True,
            )
            is_usable = bool(url)
            rejection_reason = None if is_usable else "missing_url"

            raw_records.append(
                DataRawRecord(
                    raw_object_id=raw_object.id, source_system_id=source_system.id,
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
        date_str = ingestion_run.started_at.strftime("%Y%m%d")
        filename = f"phishtank_{date_str}_{ingestion_run.id}.csv"
        return self.snapshot_store.build_object_key(
            source_prefix=self.snapshot_prefix,
            filename=filename,
        )
