from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import httpx
import pandas as pd
from langdetect import LangDetectException, detect
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from warcio.archiveiterator import ArchiveIterator

from core.config import ENV_FILE, ROOT_DIR, get_settings
from data_platform.services.common_crawl_content import CommonCrawlContentService
from data_platform.services.snapshot_storage import (
    SnapshotStore,
    SnapshotWriteResult,
    build_snapshot_store,
)

logger = logging.getLogger(__name__)

CC_WARC_BASE = "https://data.commoncrawl.org/"
DEFAULT_BATCH_SIZE = 5_000

CC_CRAWL_INDICES: tuple[str, ...] = (
    "CC-MAIN-2025-08",
    "CC-MAIN-2024-51",
    "CC-MAIN-2024-42",
    "CC-MAIN-2024-33",
    "CC-MAIN-2024-22",
    "CC-MAIN-2024-10",
    "CC-MAIN-2023-50",
    "CC-MAIN-2023-40",
    "CC-MAIN-2023-23",
    "CC-MAIN-2023-14",
    "CC-MAIN-2023-06",
    "CC-MAIN-2022-49",
    "CC-MAIN-2022-40",
    "CC-MAIN-2022-33",
    "CC-MAIN-2022-27",
    "CC-MAIN-2022-21",
    "CC-MAIN-2022-05",
    "CC-MAIN-2021-49",
    "CC-MAIN-2021-43",
    "CC-MAIN-2021-39",
    "CC-MAIN-2021-31",
    "CC-MAIN-2021-25",
    "CC-MAIN-2021-17",
    "CC-MAIN-2021-10",
    "CC-MAIN-2021-04",
    "CC-MAIN-2020-50",
    "CC-MAIN-2020-45",
    "CC-MAIN-2020-40",
    "CC-MAIN-2020-34",
    "CC-MAIN-2020-29",
    "CC-MAIN-2020-24",
    "CC-MAIN-2020-16",
    "CC-MAIN-2020-10",
    "CC-MAIN-2020-05",
    "CC-MAIN-2019-51",
    "CC-MAIN-2019-47",
    "CC-MAIN-2019-43",
    "CC-MAIN-2019-39",
    "CC-MAIN-2019-35",
    "CC-MAIN-2019-30",
)

EXCLUDED_DOMAINS = frozenset(
    {
        "phishtank.org",
        "phishtank.com",
        "cert.ssi.gouv.fr",
        "blogs.sap.com",
        "huggingface.co",
    }
)


@dataclass(frozen=True, slots=True)
class CrawlQuery:
    pattern: str
    category: str
    label: str


PHISHING_QUERIES: tuple[CrawlQuery, ...] = (
    CrawlQuery("signal-arnaques.com/*", "phishing_related", "scam_reports_fr"),
    CrawlQuery("cybermalveillance.gouv.fr/*", "phishing_related", "cert_gov_fr"),
    CrawlQuery("zataz.com/*", "phishing_related", "security_news_fr"),
    CrawlQuery("undernews.fr/*", "phishing_related", "security_news_fr"),
    CrawlQuery(
        "internet-signalement.gouv.fr/*",
        "phishing_related",
        "reporting_gov_fr",
    ),
    CrawlQuery("urlscan.io/result/*", "phishing_related", "url_scanning"),
    CrawlQuery("openphish.com/*", "phishing_related", "phishing_feed"),
    CrawlQuery("abuse.ch/*", "phishing_related", "abuse_ch"),
    CrawlQuery(
        "forum.quechoisir.org/*arnaque*",
        "phishing_related",
        "consumer_forum_fr",
    ),
    CrawlQuery(
        "forum.quechoisir.org/*phishing*",
        "phishing_related",
        "consumer_forum_fr",
    ),
    CrawlQuery(
        "commentcamarche.net/*phishing*",
        "phishing_related",
        "tech_forum_fr",
    ),
    CrawlQuery(
        "commentcamarche.net/*arnaque*",
        "phishing_related",
        "tech_forum_fr",
    ),
    CrawlQuery(
        "forums.futura-sciences.com/*arnaque*",
        "phishing_related",
        "science_forum_fr",
    ),
    CrawlQuery("signal-spam.fr/*", "phishing_related", "signal_spam_fr"),
    CrawlQuery("blog.sekoia.io/*", "phishing_related", "threat_intel_fr"),
    CrawlQuery("therecord.media/*phishing*", "phishing_related", "security_news"),
    CrawlQuery(
        "bleepingcomputer.com/*phishing*",
        "phishing_related",
        "security_news",
    ),
)

SPAM_QUERIES: tuple[CrawlQuery, ...] = (
    CrawlQuery("*.cdiscount.com/newsletter*", "spam_like", "retail_newsletter_fr"),
    CrawlQuery("*.vente-privee.com/*", "spam_like", "ecommerce_promo_fr"),
    CrawlQuery(
        "*.showroomprive.com/newsletter*",
        "spam_like",
        "ecommerce_promo_fr",
    ),
    CrawlQuery("*.dealabs.com/*", "spam_like", "deal_aggregator_fr"),
    CrawlQuery("*.darty.com/newsletter*", "spam_like", "retail_newsletter_fr"),
    CrawlQuery(
        "*.boulanger.com/newsletter*",
        "spam_like",
        "retail_newsletter_fr",
    ),
)

LEGITIMATE_QUERIES: tuple[CrawlQuery, ...] = (
    CrawlQuery("www.service-public.fr/*", "legitimate", "gov_services_fr"),
    CrawlQuery("www.economie.gouv.fr/*", "legitimate", "gov_economy_fr"),
    CrawlQuery("www.legifrance.gouv.fr/*", "legitimate", "gov_legal_fr"),
    CrawlQuery("www.education.gouv.fr/*", "legitimate", "gov_education_fr"),
    CrawlQuery("travail-emploi.gouv.fr/*", "legitimate", "gov_employment_fr"),
    CrawlQuery("www.interieur.gouv.fr/*", "legitimate", "gov_interior_fr"),
    CrawlQuery("www.ameli.fr/*", "legitimate", "health_insurance_fr"),
    CrawlQuery("www.has-sante.fr/*", "legitimate", "health_authority_fr"),
    CrawlQuery("www.sante.fr/*", "legitimate", "health_portal_fr"),
    CrawlQuery("www.mabanque.bnpparibas/*", "legitimate", "bank_fr"),
    CrawlQuery("www.credit-agricole.fr/*", "legitimate", "bank_fr"),
    CrawlQuery("www.labanquepostale.fr/*", "legitimate", "bank_fr"),
    CrawlQuery("www.societegenerale.fr/*", "legitimate", "bank_fr"),
    CrawlQuery("www.lcl.fr/*", "legitimate", "bank_fr"),
    CrawlQuery("www.edf.fr/*", "legitimate", "utility_fr"),
    CrawlQuery("www.engie.fr/*", "legitimate", "utility_fr"),
    CrawlQuery("www.orange.fr/portail*", "legitimate", "telecom_fr"),
    CrawlQuery("www.free.fr/*", "legitimate", "telecom_fr"),
    CrawlQuery("www.laposte.fr/*", "legitimate", "postal_fr"),
    CrawlQuery("www.colissimo.fr/*", "legitimate", "postal_fr"),
    CrawlQuery("www.chronopost.fr/*", "legitimate", "postal_fr"),
    CrawlQuery("www.caf.fr/*", "legitimate", "social_fr"),
    CrawlQuery("www.urssaf.fr/*", "legitimate", "social_fr"),
    CrawlQuery("www.pole-emploi.fr/*", "legitimate", "social_fr"),
    CrawlQuery("www.info-retraite.fr/*", "legitimate", "social_fr"),
)

DEFAULT_QUERIES: tuple[CrawlQuery, ...] = (
    *PHISHING_QUERIES,
    *SPAM_QUERIES,
    *LEGITIMATE_QUERIES,
)


class CommonCrawlArchiveSettings(BaseSettings):
    max_results_per_query: int = Field(
        5_000,
        validation_alias="CC_MAX_RESULTS_PER_QUERY",
    )
    max_warc_downloads: int = Field(
        1_500_000,
        validation_alias="CC_MAX_WARC_DOWNLOADS",
    )
    target_records: int = Field(600_000, validation_alias="CC_TARGET_RECORDS")
    async_concurrency: int = Field(40, validation_alias="CC_ASYNC_CONCURRENCY")
    min_text_length: int = Field(100, validation_alias="CC_MIN_TEXT_LENGTH")
    max_text_length: int = Field(10_000, validation_alias="CC_MAX_TEXT_LENGTH")
    request_timeout: int = Field(45, validation_alias="CC_REQUEST_TIMEOUT")
    batch_size: int = DEFAULT_BATCH_SIZE

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@dataclass(slots=True)
class CommonCrawlArchiveStats:
    total_index_hits: int = 0
    total_downloaded: int = 0
    extracted: int = 0
    download_errors: int = 0
    skipped_short: int = 0
    skipped_duplicate: int = 0
    per_category: dict[str, int] = field(default_factory=dict)
    per_language: dict[str, int] = field(default_factory=dict)
    seen_hashes: set[str] = field(default_factory=set, repr=False)


@dataclass(frozen=True, slots=True)
class CommonCrawlArchiveArtifacts:
    raw_storage_uri: str
    fr_usable_storage_uri: str | None
    quality_report_storage_uri: str


@dataclass(frozen=True, slots=True)
class CommonCrawlArchiveResult:
    timestamp: str
    raw_count: int
    usable_french_count: int
    artifacts: CommonCrawlArchiveArtifacts
    stats: CommonCrawlArchiveStats


class CommonCrawlArchiveStore:
    def __init__(
        self,
        *,
        snapshot_store: SnapshotStore | None = None,
        repo_root: Path = ROOT_DIR,
        backend: str | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.backend = (
            (backend or get_settings().raw_snapshot_storage_backend).strip().lower()
        )
        self.snapshot_store = snapshot_store or build_snapshot_store(
            local_root_dir=repo_root / "data",
            repo_root=repo_root,
        )

    def build_object_key(self, *, subfolder: str, filename: str) -> str:
        source_prefix = f"bigdata/common_crawl/{subfolder}"
        if self.backend != "r2":
            source_prefix = f"raw/{source_prefix}"
        return self.snapshot_store.build_object_key(
            source_prefix=source_prefix,
            filename=filename,
        )

    async def write_dataframe(
        self,
        *,
        dataframe: pd.DataFrame,
        subfolder: str,
        filename: str,
    ) -> SnapshotWriteResult:
        payload = await asyncio.to_thread(self._dataframe_to_parquet, dataframe)
        object_key = self.build_object_key(subfolder=subfolder, filename=filename)
        return await self.snapshot_store.write_snapshot(
            object_key=object_key,
            payload=payload,
            content_type="application/vnd.apache.parquet",
        )

    async def write_report(
        self,
        *,
        payload: dict[str, Any],
        filename: str,
    ) -> SnapshotWriteResult:
        encoded = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        object_key = self.build_object_key(subfolder="quality", filename=filename)
        return await self.snapshot_store.write_snapshot(
            object_key=object_key,
            payload=encoded,
            content_type="application/json",
        )

    @staticmethod
    def _dataframe_to_parquet(dataframe: pd.DataFrame) -> bytes:
        buffer = io.BytesIO()
        dataframe.to_parquet(buffer, index=False, engine="pyarrow")
        return buffer.getvalue()


class CommonCrawlArchiveExtractor:
    def __init__(
        self,
        *,
        settings: CommonCrawlArchiveSettings | None = None,
        queries: Sequence[CrawlQuery] | None = None,
        crawl_indices: Sequence[str] | None = None,
        archive_store: CommonCrawlArchiveStore | None = None,
    ) -> None:
        self.settings = settings or CommonCrawlArchiveSettings()
        self.queries = tuple(queries or DEFAULT_QUERIES)
        self.crawl_indices = tuple(crawl_indices or CC_CRAWL_INDICES)
        self.archive_store = archive_store or CommonCrawlArchiveStore()

    async def run(self) -> CommonCrawlArchiveResult:
        tracker = CommonCrawlArchiveStats()
        logger.info("=" * 60)
        logger.info("ASYNC COMMON CRAWL PIPELINE STARTING")
        logger.info("Target Records: %s", self.settings.target_records)
        logger.info("Max Downloads:  %s", self.settings.max_warc_downloads)
        logger.info("Crawl Indices:  %s", len(self.crawl_indices))
        logger.info("=" * 60)

        all_records = await self._collect_index_hits()
        if not all_records:
            raise RuntimeError("No raw index hits found.")

        raw_index_frame = self._prepare_index_frame(all_records)
        tracker.total_index_hits = len(raw_index_frame)
        logger.info(
            "Phase 1 complete. %s unique URLs ready for extraction.",
            tracker.total_index_hits,
        )

        download_frame = self._prepare_download_frame(raw_index_frame)
        extracted_pages = await self._download_warc_pages(download_frame, tracker)
        if not extracted_pages:
            raise RuntimeError("No pages extracted to upload.")

        logger.info("Phase 3: writing datasets to snapshot storage...")
        dataframe_all = pd.DataFrame(extracted_pages)
        usable_frame = self._build_usable_frame(dataframe_all)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        artifacts = await self._write_outputs(
            dataframe_all=dataframe_all,
            usable_frame=usable_frame,
            tracker=tracker,
            timestamp=timestamp,
        )

        logger.info("=" * 60)
        logger.info("COMMON CRAWL PIPELINE COMPLETE")
        logger.info("=" * 60)

        return CommonCrawlArchiveResult(
            timestamp=timestamp,
            raw_count=len(dataframe_all),
            usable_french_count=len(usable_frame),
            artifacts=artifacts,
            stats=tracker,
        )

    async def _collect_index_hits(self) -> list[dict[str, Any]]:
        logger.info("Phase 1: concurrently fetching Common Crawl index APIs...")
        all_records: list[dict[str, Any]] = []
        limits = httpx.Limits(
            max_keepalive_connections=self.settings.async_concurrency,
            max_connections=self.settings.async_concurrency + 10,
        )
        timeout = httpx.Timeout(self.settings.request_timeout)

        async with httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            index_semaphore = asyncio.Semaphore(3)
            for crawl_id in self.crawl_indices:
                if len(all_records) > self.settings.max_warc_downloads * 1.5:
                    logger.info(
                        "Sufficient index hits collected (%s). Moving to phase 2.",
                        len(all_records),
                    )
                    break

                tasks = [
                    self._fetch_index_page(client, query, crawl_id, index_semaphore)
                    for query in self.queries
                ]
                results = await asyncio.gather(*tasks)
                for records in results:
                    all_records.extend(records)
                logger.info(
                    "Index %s -> total hits so far: %s", crawl_id, len(all_records)
                )

        return all_records

    def _prepare_index_frame(self, records: list[dict[str, Any]]) -> pd.DataFrame:
        return (
            pd.DataFrame(records).drop_duplicates(subset=["url"]).reset_index(drop=True)
        )

    def _prepare_download_frame(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        filtered = dataframe.copy()
        if "status" in filtered.columns:
            filtered = filtered[filtered["status"].astype(str) == "200"]
        if "mime" in filtered.columns:
            filtered = filtered[
                filtered["mime"].astype(str).str.contains("html", case=False, na=False)
            ]
        if "_url_priority_score" in filtered.columns:
            filtered = filtered.sort_values(
                by=["_url_priority_score", "url"],
                ascending=[False, True],
            )
        return filtered.head(self.settings.max_warc_downloads).reset_index(drop=True)

    async def _download_warc_pages(
        self,
        dataframe: pd.DataFrame,
        tracker: CommonCrawlArchiveStats,
    ) -> list[dict[str, Any]]:
        logger.info(
            "Phase 2: concurrently downloading WARC records (max bounding: %s)...",
            len(dataframe),
        )
        extracted_pages: list[dict[str, Any]] = []
        limits = httpx.Limits(
            max_keepalive_connections=self.settings.async_concurrency,
            max_connections=self.settings.async_concurrency + 10,
        )
        timeout = httpx.Timeout(self.settings.request_timeout)

        async with httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            semaphore = asyncio.Semaphore(self.settings.async_concurrency)
            for start in range(0, len(dataframe), self.settings.batch_size):
                if tracker.extracted >= self.settings.target_records:
                    break

                batch_rows = dataframe.iloc[
                    start : start + self.settings.batch_size
                ].to_dict("records")
                logger.info(
                    "  -> Awaiting WARC batch %s to %s...",
                    start,
                    start + len(batch_rows),
                )
                tasks = [
                    self._fetch_warc_record(client, row, semaphore, tracker)
                    for row in batch_rows
                ]
                results = await asyncio.gather(*tasks)
                extracted_pages.extend(page for page in results if page is not None)
                logger.info(
                    "  Progress: Downloaded=%s, Extracted=%s",
                    tracker.total_downloaded,
                    tracker.extracted,
                )

        return extracted_pages

    async def _write_outputs(
        self,
        *,
        dataframe_all: pd.DataFrame,
        usable_frame: pd.DataFrame,
        tracker: CommonCrawlArchiveStats,
        timestamp: str,
    ) -> CommonCrawlArchiveArtifacts:
        raw_filename = f"common_crawl_raw_{len(dataframe_all)}_{timestamp}.parquet"
        raw_result = await self.archive_store.write_dataframe(
            dataframe=dataframe_all,
            subfolder="raw",
            filename=raw_filename,
        )

        usable_storage_uri: str | None = None
        if not usable_frame.empty:
            usable_filename = (
                f"common_crawl_fr_usable_{len(usable_frame)}_{timestamp}.parquet"
            )
            usable_result = await self.archive_store.write_dataframe(
                dataframe=usable_frame,
                subfolder="fr_usable",
                filename=usable_filename,
            )
            usable_storage_uri = usable_result.storage_uri

        report_filename = f"quality_report_{timestamp}.json"
        report = self.build_quality_report(
            timestamp=timestamp,
            settings=self.settings,
            tracker=tracker,
            usable_french_count=len(usable_frame),
        )
        report_result = await self.archive_store.write_report(
            payload=report,
            filename=report_filename,
        )
        return CommonCrawlArchiveArtifacts(
            raw_storage_uri=raw_result.storage_uri,
            fr_usable_storage_uri=usable_storage_uri,
            quality_report_storage_uri=report_result.storage_uri,
        )

    def _build_usable_frame(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        return dataframe[
            (dataframe["language"] == "fr")
            & (dataframe["text_length"] >= self.settings.min_text_length)
        ].reset_index(drop=True)

    async def _fetch_index_page(
        self,
        client: httpx.AsyncClient,
        query: CrawlQuery,
        crawl_id: str,
        semaphore: asyncio.Semaphore,
    ) -> list[dict[str, Any]]:
        url = f"https://index.commoncrawl.org/{crawl_id}-index"
        params = {
            "url": query.pattern,
            "output": "json",
            "limit": str(self.settings.max_results_per_query),
        }

        async with semaphore:
            for attempt in range(4):
                try:
                    response = await client.get(url, params=params)
                    if response.status_code in (429, 503):
                        await asyncio.sleep(2**attempt)
                        continue
                    response.raise_for_status()
                    return self._parse_index_payload(
                        payload=response.text,
                        query=query,
                        crawl_id=crawl_id,
                    )
                except Exception as exc:
                    if attempt == 3:
                        logger.debug(
                            "Failed query %s on %s after retries: %s",
                            query.pattern,
                            crawl_id,
                            exc,
                        )
                    await asyncio.sleep(2**attempt)
        return []

    def _parse_index_payload(
        self,
        *,
        payload: str,
        query: CrawlQuery,
        crawl_id: str,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for line in payload.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            record = json.loads(stripped)
            if self.is_excluded_domain(record.get("url", "")):
                continue
            record.update(
                {
                    "_category": query.category,
                    "_label": query.label,
                    "_query": query.pattern,
                    "_crawl_id": crawl_id,
                    "_url_priority_score": CommonCrawlContentService.score_url(
                        record.get("url", ""),
                        query.category,
                    ),
                }
            )
            records.append(record)
        return records

    async def _fetch_warc_record(
        self,
        client: httpx.AsyncClient,
        row: dict[str, Any],
        semaphore: asyncio.Semaphore,
        tracker: CommonCrawlArchiveStats,
    ) -> dict[str, Any] | None:
        if tracker.extracted >= self.settings.target_records:
            return None

        offset = int(row["offset"])
        end = offset + int(row["length"]) - 1
        headers = {"Range": f"bytes={offset}-{end}"}
        warc_url = f"{CC_WARC_BASE}{row['filename']}"

        async with semaphore:
            try:
                response = await client.get(warc_url, headers=headers)
                if response.status_code not in (200, 206):
                    tracker.download_errors += 1
                    return None

                tracker.total_downloaded += 1
                stream = io.BytesIO(response.content)
                for record in ArchiveIterator(stream):
                    if record.rec_type != "response":
                        continue
                    html_text = (
                        record.content_stream()
                        .read()
                        .decode(
                            "utf-8",
                            errors="replace",
                        )
                    )
                    text = CommonCrawlContentService.extract_text_from_html(
                        html_text,
                        max_length=self.settings.max_text_length,
                    )
                    if len(text) < self.settings.min_text_length:
                        tracker.skipped_short += 1
                        return None

                    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
                    if content_hash in tracker.seen_hashes:
                        tracker.skipped_duplicate += 1
                        return None

                    tracker.seen_hashes.add(content_hash)
                    language = self.detect_language(text)
                    tracker.per_language[language] = (
                        tracker.per_language.get(language, 0) + 1
                    )
                    tracker.per_category[row["_category"]] = (
                        tracker.per_category.get(row["_category"], 0) + 1
                    )
                    tracker.extracted += 1
                    return {
                        "url": row["url"],
                        "text": text,
                        "text_length": len(text),
                        "language": language,
                        "category": row["_category"],
                        "label": row["_category"],
                        "query_label": row["_label"],
                        "query": row["_query"],
                        "crawl_id": row["_crawl_id"],
                        "url_priority_score": row.get("_url_priority_score", 0),
                        "content_hash": content_hash,
                    }
            except Exception:
                tracker.download_errors += 1
                return None
        return None

    @staticmethod
    def is_excluded_domain(url: str) -> bool:
        try:
            domain = url.split("//", 1)[-1].split("/", 1)[0].lower()
        except Exception:
            return False
        return any(excluded in domain for excluded in EXCLUDED_DOMAINS)

    @staticmethod
    def detect_language(text: str) -> str:
        try:
            return detect(text[:1500])
        except LangDetectException:
            return "unknown"

    @staticmethod
    def build_quality_report(
        *,
        timestamp: str,
        settings: CommonCrawlArchiveSettings,
        tracker: CommonCrawlArchiveStats,
        usable_french_count: int,
    ) -> dict[str, Any]:
        return {
            "extraction_date": timestamp,
            "config": {
                "async_concurrency": settings.async_concurrency,
                "target_records": settings.target_records,
                "max_warc_downloads": settings.max_warc_downloads,
                "max_results_per_query": settings.max_results_per_query,
                "min_text_length": settings.min_text_length,
                "max_text_length": settings.max_text_length,
                "request_timeout": settings.request_timeout,
            },
            "stats": {
                "total_index_hits": tracker.total_index_hits,
                "total_downloaded": tracker.total_downloaded,
                "total_extracted": tracker.extracted,
                "download_errors": tracker.download_errors,
                "usable_french": usable_french_count,
                "skipped_short": tracker.skipped_short,
                "skipped_duplicate": tracker.skipped_duplicate,
            },
            "language_distribution": tracker.per_language,
            "category_distribution": tracker.per_category,
        }
