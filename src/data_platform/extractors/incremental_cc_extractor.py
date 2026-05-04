"""Incremental Common Crawl extractor for cron — resumable and time-bounded.

This module is a standalone extractor that:
1. Dynamically discovers all available CC indices from collinfo.json.
2. Reads the last completed index from the ``pipeline_state`` DB table.
3. Processes missing indices one-by-one from oldest to newest.
4. Enforces a maximum runtime; partial results are flushed to R2.
5. Updates the checkpoint after each completed index.

It does NOT modify or import the original ``common_crawl_archive.py``
which is reserved for the immutable base dataset.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import httpx
import pandas as pd
from langdetect import LangDetectException, detect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import ROOT_DIR
from data_platform.services.common_crawl.content import CommonCrawlContentService
from data_platform.services.shared.snapshot_storage import (
    SnapshotStore,
    build_snapshot_store,
)
from db.models import PipelineState

logger = logging.getLogger(__name__)

CC_WARC_BASE = "https://data.commoncrawl.org/"
COLLINFO_URL = "https://index.commoncrawl.org/collinfo.json"
PIPELINE_NAME = "common_crawl_cron"
COMMON_CRAWL_REQUEST_HEADERS = {
    "User-Agent": "sicurre-common-crawl/1.0",
    "Accept": "application/json, text/plain, */*",
}

# The last index that base fully covered — everything after this is cron territory
BASE_CUTOFF_INDEX = "CC-MAIN-2025-08"

DURATION_MAP: dict[str, int] = {
    "short": 30 * 60,  # 30 minutes
    "standard": 8 * 60 * 60,  # 8 hours
}

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


# Same queries as base — we want the same data profile
PHISHING_QUERIES: tuple[CrawlQuery, ...] = (
    CrawlQuery("signal-arnaques.com/*", "phishing_related", "scam_reports_fr"),
    CrawlQuery("cybermalveillance.gouv.fr/*", "phishing_related", "cert_gov_fr"),
    CrawlQuery("zataz.com/*", "phishing_related", "security_news_fr"),
    CrawlQuery("undernews.fr/*", "phishing_related", "security_news_fr"),
    CrawlQuery(
        "internet-signalement.gouv.fr/*", "phishing_related", "reporting_gov_fr"
    ),
    CrawlQuery("urlscan.io/result/*", "phishing_related", "url_scanning"),
    CrawlQuery("openphish.com/*", "phishing_related", "phishing_feed"),
    CrawlQuery("abuse.ch/*", "phishing_related", "abuse_ch"),
    CrawlQuery(
        "forum.quechoisir.org/*arnaque*", "phishing_related", "consumer_forum_fr"
    ),
    CrawlQuery(
        "forum.quechoisir.org/*phishing*", "phishing_related", "consumer_forum_fr"
    ),
    CrawlQuery("commentcamarche.net/*phishing*", "phishing_related", "tech_forum_fr"),
    CrawlQuery("commentcamarche.net/*arnaque*", "phishing_related", "tech_forum_fr"),
    CrawlQuery(
        "forums.futura-sciences.com/*arnaque*", "phishing_related", "science_forum_fr"
    ),
    CrawlQuery("signal-spam.fr/*", "phishing_related", "signal_spam_fr"),
    CrawlQuery("blog.sekoia.io/*", "phishing_related", "threat_intel_fr"),
    CrawlQuery("therecord.media/*phishing*", "phishing_related", "security_news"),
    CrawlQuery("bleepingcomputer.com/*phishing*", "phishing_related", "security_news"),
)

SPAM_QUERIES: tuple[CrawlQuery, ...] = (
    CrawlQuery("*.cdiscount.com/newsletter*", "spam_like", "retail_newsletter_fr"),
    CrawlQuery("*.vente-privee.com/*", "spam_like", "ecommerce_promo_fr"),
    CrawlQuery("*.showroomprive.com/newsletter*", "spam_like", "ecommerce_promo_fr"),
    CrawlQuery("*.dealabs.com/*", "spam_like", "deal_aggregator_fr"),
    CrawlQuery("*.darty.com/newsletter*", "spam_like", "retail_newsletter_fr"),
    CrawlQuery("*.boulanger.com/newsletter*", "spam_like", "retail_newsletter_fr"),
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


@dataclass(slots=True)
class IncrementalCCStats:
    indices_processed: int = 0
    total_index_hits: int = 0
    total_downloaded: int = 0
    extracted: int = 0
    download_errors: int = 0
    skipped_short: int = 0
    skipped_duplicate: int = 0
    per_category: dict[str, int] = field(default_factory=dict)
    per_language: dict[str, int] = field(default_factory=dict)
    seen_hashes: set[str] = field(default_factory=set, repr=False)
    timed_out: bool = False


@dataclass(frozen=True, slots=True)
class IncrementalCCResult:
    indices_attempted: list[str]
    indices_completed: list[str]
    total_extracted: int
    timed_out: bool
    r2_uris: list[str]
    stats: IncrementalCCStats


class IncrementalCommonCrawlExtractor:
    """Resumable, time-bounded Common Crawl extractor for cron jobs.

    Processes one CC index at a time. After each index, flushes results
    to R2 and updates the checkpoint in the database. If the time limit
    is reached during an index, the partial results are still flushed.
    """

    def __init__(
        self,
        *,
        max_runtime_seconds: int = DURATION_MAP["short"],
        queries: Sequence[CrawlQuery] | None = None,
        snapshot_store: SnapshotStore | None = None,
        max_results_per_query: int = 5_000,
        max_warc_downloads_per_index: int = 50_000,
        async_concurrency: int = 40,
        min_text_length: int = 100,
        max_text_length: int = 10_000,
        request_timeout: int = 45,
    ) -> None:
        self.max_runtime_seconds = max_runtime_seconds
        self.queries = tuple(queries or DEFAULT_QUERIES)
        self.max_results_per_query = max_results_per_query
        self.max_warc_downloads_per_index = max_warc_downloads_per_index
        self.async_concurrency = async_concurrency
        self.min_text_length = min_text_length
        self.max_text_length = max_text_length
        self.request_timeout = request_timeout
        self.snapshot_store = snapshot_store or build_snapshot_store(
            local_root_dir=ROOT_DIR / "data",
            repo_root=ROOT_DIR,
            source_key="common_crawl",
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self, session: AsyncSession) -> IncrementalCCResult:
        """Execute the incremental extraction pipeline."""
        start_time = time.monotonic()
        stats = IncrementalCCStats()

        logger.info("=" * 60)
        logger.info("INCREMENTAL COMMON CRAWL CRON STARTING")
        logger.info(
            "Max runtime: %d seconds (%d min)",
            self.max_runtime_seconds,
            self.max_runtime_seconds // 60,
        )
        logger.info("=" * 60)

        # 1. Discover all available indices
        all_indices = await self._fetch_available_indices()
        if not all_indices:
            raise RuntimeError(
                "Failed to fetch Common Crawl index list from collinfo.json"
            )

        logger.info(
            "Available CC indices: %d (latest: %s)", len(all_indices), all_indices[0]
        )

        # 2. Read checkpoint from DB
        last_completed = await self._read_checkpoint(session)
        logger.info(
            "Last completed index (checkpoint): %s", last_completed or BASE_CUTOFF_INDEX
        )

        # 3. Compute the missing indices (after base cutoff or last checkpoint)
        cutoff = last_completed or BASE_CUTOFF_INDEX
        missing_indices = self._compute_missing_indices(all_indices, cutoff)
        logger.info(
            "Missing indices to process: %d — %s", len(missing_indices), missing_indices
        )

        if not missing_indices:
            logger.info("All available indices already processed. Nothing to do.")
            return IncrementalCCResult(
                indices_attempted=[],
                indices_completed=[],
                total_extracted=0,
                timed_out=False,
                r2_uris=[],
                stats=stats,
            )

        # 4. Process indices one by one
        indices_attempted: list[str] = []
        indices_completed: list[str] = []
        r2_uris: list[str] = []

        for crawl_id in missing_indices:
            elapsed = time.monotonic() - start_time
            if elapsed >= self.max_runtime_seconds:
                logger.info(
                    "Time limit reached (%d s). Stopping gracefully.", int(elapsed)
                )
                stats.timed_out = True
                break

            indices_attempted.append(crawl_id)
            logger.info("--- Processing index: %s ---", crawl_id)

            try:
                pages = await self._process_single_index(crawl_id, stats, start_time)
            except Exception as exc:
                logger.error("Failed to process index %s: %s", crawl_id, exc)
                # Still flush whatever we got
                pages = []

            # Flush results to R2 even if partial
            if pages:
                uri = await self._flush_to_r2(crawl_id, pages)
                r2_uris.append(uri)
                logger.info("Flushed %d pages from %s → %s", len(pages), crawl_id, uri)

            # Check if we timed out mid-index
            elapsed = time.monotonic() - start_time
            if elapsed >= self.max_runtime_seconds:
                logger.info(
                    "Time limit reached mid-index %s after %d s. Partial flush done.",
                    crawl_id,
                    int(elapsed),
                )
                stats.timed_out = True
                # Still update checkpoint since we flushed what we had
                await self._update_checkpoint(session, crawl_id)
                indices_completed.append(crawl_id)
                break

            # Full index completed — update checkpoint
            await self._update_checkpoint(session, crawl_id)
            indices_completed.append(crawl_id)
            stats.indices_processed += 1
            logger.info("Checkpoint updated: %s completed.", crawl_id)

        logger.info("=" * 60)
        logger.info("INCREMENTAL CC CRON COMPLETE")
        logger.info(
            "Processed: %d indices, Extracted: %d pages",
            len(indices_completed),
            stats.extracted,
        )
        logger.info("Timed out: %s", stats.timed_out)
        logger.info("=" * 60)

        return IncrementalCCResult(
            indices_attempted=indices_attempted,
            indices_completed=indices_completed,
            total_extracted=stats.extracted,
            timed_out=stats.timed_out,
            r2_uris=r2_uris,
            stats=stats,
        )

    # ------------------------------------------------------------------
    # Index discovery
    # ------------------------------------------------------------------

    async def _fetch_available_indices(self) -> list[str]:
        """Fetch the live list of CC indices from collinfo.json."""
        async with httpx.AsyncClient(
            headers=COMMON_CRAWL_REQUEST_HEADERS,
            timeout=30,
            follow_redirects=True,
        ) as client:
            resp = await client.get(COLLINFO_URL)
            resp.raise_for_status()
            return [item["id"] for item in resp.json() if "id" in item]

    @staticmethod
    def _compute_missing_indices(all_indices: list[str], cutoff: str) -> list[str]:
        """Return indices that are newer than the cutoff, from oldest to newest."""
        try:
            cutoff_pos = all_indices.index(cutoff)
        except ValueError:
            # Cutoff not found — treat everything as potentially missing
            cutoff_pos = len(all_indices)

        # all_indices is newest-first, so everything before cutoff_pos is newer
        missing = all_indices[:cutoff_pos]
        missing.reverse()  # oldest first so we process chronologically
        return missing

    # ------------------------------------------------------------------
    # Single index processing
    # ------------------------------------------------------------------

    async def _process_single_index(
        self,
        crawl_id: str,
        stats: IncrementalCCStats,
        start_time: float,
    ) -> list[dict[str, Any]]:
        """Fetch index hits and download WARC pages for a single CC index."""
        from warcio.archiveiterator import ArchiveIterator

        # Phase 1: Collect index hits
        index_hits = await self._collect_index_hits_for_crawl(crawl_id)
        if not index_hits:
            logger.info("No index hits for %s", crawl_id)
            return []

        stats.total_index_hits += len(index_hits)

        # Phase 2: Download WARC pages
        df = (
            pd.DataFrame(index_hits)
            .drop_duplicates(subset=["url"])
            .reset_index(drop=True)
        )

        # Filter for 200s and HTML
        if "status" in df.columns:
            df = df[df["status"].astype(str) == "200"]
        if "mime" in df.columns:
            df = df[df["mime"].astype(str).str.contains("html", case=False, na=False)]

        limit = min(self.max_warc_downloads_per_index, len(df))
        df = df.head(limit).reset_index(drop=True)
        logger.info(
            "Index %s: %d unique URLs ready for WARC download.", crawl_id, len(df)
        )

        extracted_pages: list[dict[str, Any]] = []
        limits = httpx.Limits(
            max_keepalive_connections=self.async_concurrency,
            max_connections=self.async_concurrency + 10,
        )
        timeout = httpx.Timeout(self.request_timeout)

        async with httpx.AsyncClient(
            headers=COMMON_CRAWL_REQUEST_HEADERS,
            limits=limits,
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            semaphore = asyncio.Semaphore(self.async_concurrency)
            batch_size = 5_000

            for batch_start in range(0, len(df), batch_size):
                # Check time budget before each batch
                elapsed = time.monotonic() - start_time
                if elapsed >= self.max_runtime_seconds:
                    logger.info(
                        "Time limit reached during WARC downloads for %s", crawl_id
                    )
                    break

                batch_rows = df.iloc[batch_start : batch_start + batch_size].to_dict(
                    "records"
                )
                tasks = [
                    self._fetch_warc_record(client, row, semaphore, stats)
                    for row in batch_rows
                ]
                results = await asyncio.gather(*tasks)
                extracted_pages.extend(page for page in results if page is not None)
                logger.info(
                    "  [%s] batch %d-%d: downloaded=%d, extracted=%d",
                    crawl_id,
                    batch_start,
                    batch_start + len(batch_rows),
                    stats.total_downloaded,
                    stats.extracted,
                )

        return extracted_pages

    async def _collect_index_hits_for_crawl(
        self, crawl_id: str
    ) -> list[dict[str, Any]]:
        """Query the CC index API for all configured queries against a single crawl."""
        all_records: list[dict[str, Any]] = []
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=15)
        timeout = httpx.Timeout(self.request_timeout)

        async with httpx.AsyncClient(
            headers=COMMON_CRAWL_REQUEST_HEADERS,
            limits=limits,
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            semaphore = asyncio.Semaphore(3)
            tasks = [
                self._fetch_index_page(client, query, crawl_id, semaphore)
                for query in self.queries
            ]
            results = await asyncio.gather(*tasks)
            for records in results:
                all_records.extend(records)

        logger.info("Index %s → %d raw hits", crawl_id, len(all_records))
        return all_records

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
            "limit": str(self.max_results_per_query),
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
                            "Failed query %s on %s: %s", query.pattern, crawl_id, exc
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
            url = record.get("url", "")
            if self._is_excluded_domain(url):
                continue
            record.update(
                {
                    "_category": query.category,
                    "_label": query.label,
                    "_query": query.pattern,
                    "_crawl_id": crawl_id,
                    "_url_priority_score": CommonCrawlContentService.score_url(
                        url, query.category
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
        stats: IncrementalCCStats,
    ) -> dict[str, Any] | None:
        from warcio.archiveiterator import ArchiveIterator

        offset = int(row["offset"])
        end = offset + int(row["length"]) - 1
        headers = {
            **COMMON_CRAWL_REQUEST_HEADERS,
            "Range": f"bytes={offset}-{end}",
        }
        warc_url = f"{CC_WARC_BASE}{row['filename']}"

        async with semaphore:
            try:
                response = await client.get(warc_url, headers=headers)
                if response.status_code not in (200, 206):
                    stats.download_errors += 1
                    return None

                stats.total_downloaded += 1
                stream = io.BytesIO(response.content)
                for record in ArchiveIterator(stream):
                    if record.rec_type != "response":
                        continue
                    html_text = (
                        record.content_stream().read().decode("utf-8", errors="replace")
                    )
                    text = CommonCrawlContentService.extract_text_from_html(
                        html_text,
                        max_length=self.max_text_length,
                    )
                    if len(text) < self.min_text_length:
                        stats.skipped_short += 1
                        return None

                    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
                    if content_hash in stats.seen_hashes:
                        stats.skipped_duplicate += 1
                        return None

                    stats.seen_hashes.add(content_hash)
                    language = self._detect_language(text)
                    stats.per_language[language] = (
                        stats.per_language.get(language, 0) + 1
                    )
                    stats.per_category[row["_category"]] = (
                        stats.per_category.get(row["_category"], 0) + 1
                    )
                    stats.extracted += 1
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
                        "content_hash": content_hash,
                    }
            except Exception:
                stats.download_errors += 1
                return None
        return None

    # ------------------------------------------------------------------
    # R2 flush
    # ------------------------------------------------------------------

    async def _flush_to_r2(self, crawl_id: str, pages: list[dict[str, Any]]) -> str:
        """Write extracted pages to R2 mirroring the base dataset structure (raw, fr_usable, quality)."""
        df = pd.DataFrame(pages)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base_prefix = f"cron/bigdata/common_crawl/{crawl_id}/{timestamp}"

        # 1. Save raw data
        raw_buffer = io.BytesIO()
        df.to_parquet(raw_buffer, index=False, engine="pyarrow")
        raw_key = self.snapshot_store.build_object_key(
            source_prefix=f"{base_prefix}/raw",
            filename=f"cc_incremental_raw_{len(df)}_{timestamp}.parquet",
        )
        await self.snapshot_store.write_snapshot(
            object_key=raw_key,
            payload=raw_buffer.getvalue(),
            content_type="application/vnd.apache.parquet",
        )

        # 2. Save fr_usable data
        fr_df = df[df["language"] == "fr"].copy() if not df.empty else df.copy()
        fr_buffer = io.BytesIO()
        fr_df.to_parquet(fr_buffer, index=False, engine="pyarrow")
        fr_key = self.snapshot_store.build_object_key(
            source_prefix=f"{base_prefix}/fr_usable",
            filename=f"cc_incremental_fr_usable_{len(fr_df)}_{timestamp}.parquet",
        )
        await self.snapshot_store.write_snapshot(
            object_key=fr_key,
            payload=fr_buffer.getvalue(),
            content_type="application/vnd.apache.parquet",
        )

        # 3. Save quality report
        quality_report = {
            "index": crawl_id,
            "timestamp": timestamp,
            "total_extracted": len(df),
            "fr_usable_count": len(fr_df),
            "language_distribution": (
                df["language"].value_counts().to_dict() if not df.empty else {}
            ),
            "category_distribution": (
                df["category"].value_counts().to_dict() if not df.empty else {}
            ),
        }
        quality_key = self.snapshot_store.build_object_key(
            source_prefix=f"{base_prefix}/quality",
            filename=f"quality_report_{timestamp}.json",
        )
        await self.snapshot_store.write_snapshot(
            object_key=quality_key,
            payload=json.dumps(quality_report, indent=2).encode("utf-8"),
            content_type="application/json",
        )

        return raw_key

    # ------------------------------------------------------------------
    # Checkpoint (DB-backed)
    # ------------------------------------------------------------------

    @staticmethod
    async def _read_checkpoint(session: AsyncSession) -> str | None:
        """Read the last completed CC index from the pipeline_state table."""
        stmt = select(PipelineState).where(PipelineState.pipeline_name == PIPELINE_NAME)
        row = await session.scalar(stmt)
        if row is None:
            return None
        return row.state_data.get("last_completed_index")

    @staticmethod
    async def _update_checkpoint(session: AsyncSession, crawl_id: str) -> None:
        """Update the checkpoint with the last completed CC index."""
        stmt = select(PipelineState).where(PipelineState.pipeline_name == PIPELINE_NAME)
        row = await session.scalar(stmt)
        now = datetime.now(timezone.utc)
        if row is None:
            row = PipelineState(
                pipeline_name=PIPELINE_NAME,
                state_data={
                    "last_completed_index": crawl_id,
                    "updated_at": now.isoformat(),
                },
            )
            session.add(row)
        else:
            row.state_data = {
                **row.state_data,
                "last_completed_index": crawl_id,
                "updated_at": now.isoformat(),
            }
        await session.commit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_excluded_domain(url: str) -> bool:
        try:
            domain = url.split("//", 1)[-1].split("/", 1)[0].lower()
        except Exception:
            return False
        return any(excluded in domain for excluded in EXCLUDED_DOMAINS)

    @staticmethod
    def _detect_language(text: str) -> str:
        try:
            return detect(text[:1500])
        except LangDetectException:
            return "unknown"
