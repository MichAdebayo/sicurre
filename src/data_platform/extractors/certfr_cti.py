"""CERT-FR CTI content extraction — single-pass automated job.

Discovers new CTI and IOC reports via the paginated CERT-FR indexes,
downloads the PDF (or scrapes the web page when no PDF exists), extracts
text and IOCs, and stores everything in a single ``DataIngestionRun``.

Designed to run **bi-weekly** via an external scheduler (cron / Cloud
Scheduler).  Most runs will find zero new reports and exit cheaply.
"""

from __future__ import annotations

import asyncio
import io
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import ROOT_DIR
from core.trace_logger import SemanticTraceLogger
from data_platform.api.schemas import (
    DataSourceCreate,
    IngestionRunCreate,
)
from data_platform.services.shared.snapshot_storage import (
    SnapshotStore,
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
from db.services.lineage import (
    IngestionRunService,
    SourceSystemService,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = ROOT_DIR
CERTFR_PDF_BASE = "https://www.cert.ssi.gouv.fr/uploads"
CERTFR_REFERENCE_RE = re.compile(r"(CERTFR-\d{4}-(?:CTI|IOC)-\d+)", re.IGNORECASE)
DEFAULT_SOURCE_NAME = "cert-fr-cti"
DEFAULT_SNAPSHOT_DIR = REPO_ROOT / "data" / "raw" / "scraping" / "cert_fr"
DEFAULT_SNAPSHOT_PREFIX = "cert-fr"

# IOC extraction patterns
_DOMAIN_RE = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"(?:com|org|net|fr|io|de|ru|cn|uk|info|gov|mil|edu)\b"
)
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}" r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)
_HASH_RE = re.compile(r"\b[a-fA-F0-9]{32,64}\b")

# French phishing relevance keywords
_PHISHING_KEYWORDS: frozenset[str] = frozenset(
    (
        "hameçonnage",
        "hameconnage",
        "phishing",
        "ingénierie sociale",
        "social engineering",
        "usurpation",
        "courriel malveillant",
        "courriels malveillants",
        "fraude",
        "arnaque",
        "rançongiciel",
        "ransomware",
        "campagne",
        "malveillant",
        "spam",
        "spear",
        "credential",
        "vol de données",
        "exfiltration",
    )
)

# Noise domains to exclude from IOC extraction
_NOISE_DOMAINS: frozenset[str] = frozenset(
    (
        "cert.ssi.gouv.fr",
        "ssi.gouv.fr",
        "gouv.fr",
        "anssi.fr",
        "apple.com",
        "microsoft.com",
        "google.com",
        "github.com",
        "example.com",
        "example.org",
    )
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExtractedContent:
    """Result of extracting text and IOCs from a single CTI report."""

    reference: str
    title: str
    text: str
    text_length: int
    extraction_method: str  # "pdfplumber" | "html_scraping"
    source_url: str
    domains: list[str]
    emails: list[str]
    ips: list[str]
    hashes: list[str]
    is_phishing_related: bool


@dataclass(slots=True)
class CertFRCtiResult:
    """Summary of one extraction run."""

    ingestion_run_id: str
    source_system_id: str
    discovered_count: int
    new_count: int
    extracted_count: int
    skipped_count: int
    failed_count: int
    reports: list[ExtractedContent] = field(default_factory=list)
    log_message: str = ""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class CertFRCtiExtractor:
    """Single-pass CERT-FR CTI extraction job.

    1. Crawl the CERT-FR CTI/IOC indexes to discover available reports.
    2. Skip reports already stored (dedup by ``external_ref``).
    3. For each new report, try downloading the PDF; fall back to HTML.
    4. Extract text, IOCs, and phishing relevance.
    5. Store everything in one ``DataIngestionRun``.
    """

    def __init__(
        self,
        *,
        pdf_base_url: str = CERTFR_PDF_BASE,
        discover_entries: (
            Callable[[bool], Awaitable[list[dict[str, Any]]]] | None
        ) = None,
        download_url: Callable[[str], Awaitable[httpx.Response]] | None = None,
        snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
        snapshot_store: SnapshotStore | None = None,
        snapshot_prefix: str = DEFAULT_SNAPSHOT_PREFIX,
        source_name: str = DEFAULT_SOURCE_NAME,
        timeout_seconds: float = 30.0,
        delay_between_requests: float = 2.0,
        max_discovery_pages: int | None = 3,
    ) -> None:
        self.pdf_base_url = pdf_base_url.rstrip("/")
        self._discover_entries_override = discover_entries
        self._download_url = download_url
        self.snapshot_dir = snapshot_dir
        self.snapshot_prefix = snapshot_prefix
        self.source_name = source_name
        self.timeout_seconds = timeout_seconds
        self.delay_between_requests = delay_between_requests
        self.max_discovery_pages = max_discovery_pages

        local_root = (
            snapshot_dir.parent
            if snapshot_dir.name == snapshot_prefix
            else snapshot_dir
        )
        self.snapshot_store = snapshot_store or build_snapshot_store(
            local_root_dir=local_root,
            repo_root=REPO_ROOT,
            source_key="certfr",
        )
        self.source_service = SourceSystemService()
        self.ingestion_service = IngestionRunService()
        self.source_repository = SourceSystemQueries()

    # ------------------------------------------------------------------
    # Public entry point
    async def run(
        self,
        session: AsyncSession,
        *,
        trigger_mode: str = "scheduled",
        started_at: datetime | None = None,
        fetch_historical: bool = False,
    ) -> CertFRCtiResult:
        run_started_at = started_at or datetime.now(timezone.utc)

        trace = SemanticTraceLogger(
            parent_type="Web Scraping",
            child_target="CERT-FR CTI",
            domain="data_platform",
        )
        trace.trace(
            stage="orchestration",
            status="start",
            message="Initializing CERT-FR CTI Scraper.",
        )

        source_system = await self._get_or_create_source(session)
        ingestion_run = await self.ingestion_service.create(
            session,
            IngestionRunCreate(
                source_system_id=source_system.id,
                started_at=run_started_at,
                status=IngestionStatus.RUNNING,
                trigger_mode=trigger_mode,
                log_message="CERT-FR CTI extraction started",
            ),
        )

        trace.set_trace_id(str(ingestion_run.id))
        trace.trace(
            stage="ingestion",
            status="start",
            entity_type="DataIngestionRun",
            entity_id=str(ingestion_run.id),
            message="Discovering CERT-FR CTI and IOC entries from paginated indexes...",
        )

        result = CertFRCtiResult(
            ingestion_run_id=str(ingestion_run.id),
            source_system_id=str(source_system.id),
            discovered_count=0,
            new_count=0,
            extracted_count=0,
            skipped_count=0,
            failed_count=0,
        )

        try:
            entries = await self._discover_entries(fetch_historical=fetch_historical)
            result.discovered_count = len(entries)

            if not entries:
                result.log_message = (
                    "No CERT-FR CTI or IOC entries found in paginated indexes"
                )
                await self._finish_run(ingestion_run, IngestionStatus.COMPLETED, result)
                await session.commit()
                trace.trace(
                    stage="ingestion",
                    status="success",
                    metrics={"discovered_count": 0},
                    message="CERT-FR paginated indexes returned 0 entries — nothing to parse.",
                )
                return result

            existing_refs = await self._existing_references(session)
            new_entries = [
                e
                for e in entries
                if e.get("reference") and e["reference"] not in existing_refs
            ]
            result.new_count = len(new_entries)

            if not new_entries:
                result.skipped_count = result.discovered_count
                result.log_message = (
                    f"All {result.discovered_count} CTI reports already "
                    f"extracted — nothing new"
                )
                await self._finish_run(ingestion_run, IngestionStatus.COMPLETED, result)
                await session.commit()

                trace.trace(
                    stage="ingestion",
                    status="success",
                    metrics={
                        "discovered": result.discovered_count,
                        "skipped": result.skipped_count,
                    },
                    message=f"All {result.discovered_count} parsed PDF reports already exist in DB — skipped gracefully.",
                )
                return result

            for entry in new_entries:
                try:
                    content = await self._extract_report(entry)
                    raw_object, raw_record = await self._persist_content(
                        session,
                        ingestion_run=ingestion_run,
                        source_system=source_system,
                        content=content,
                        collected_at=run_started_at,
                    )

                    trace.trace(
                        stage="extraction",
                        status="success",
                        entity_type="DataRawRecord",
                        entity_id=str(raw_record.id),
                        message=f"Successfully extracted CTI text from {content.extraction_method} for {entry.get('reference')}",
                    )

                    result.extracted_count += 1
                    result.reports.append(content)
                except Exception as exc:
                    result.failed_count += 1
                    ref = entry.get("reference", "unknown")
                    result.log_message += f"\n⚠ {ref}: extraction failed — {exc}"

                if self.delay_between_requests > 0:
                    await asyncio.sleep(self.delay_between_requests)

            result.skipped_count = result.discovered_count - result.new_count
            status = (
                IngestionStatus.COMPLETED
                if result.failed_count == 0
                else IngestionStatus.PARTIAL
            )
            result.log_message = self._build_summary(result) + (
                result.log_message or ""
            )
            await self._finish_run(ingestion_run, status, result)
            await session.commit()

            trace.trace(
                stage="orchestration",
                status="success",
                metrics={
                    "new_reports": result.extracted_count,
                    "skipped": result.skipped_count,
                    "failed": result.failed_count,
                },
                message=f"CERT-FR extraction cycle completed. Processed {result.extracted_count} new reports.",
            )

            return result

        except Exception as exc:
            ingestion_run.finished_at = datetime.now(timezone.utc)
            ingestion_run.status = IngestionStatus.FAILED
            ingestion_run.log_message = f"CERT-FR CTI extraction failed: {exc}"
            await session.commit()

            trace.trace(
                stage="ingestion",
                status="failed",
                message=f"Catastrophic failure during CERT-FR extraction: {str(exc)}",
            )

            raise

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    async def _discover_entries(
        self, fetch_historical: bool = False
    ) -> list[dict[str, Any]]:
        """Discover CTI and IOC entries from the paginated CERT-FR indexes.

        - Scheduled/manual incremental runs cap discovery to
          ``self.max_discovery_pages`` pages per base URL.
        - Historical runs crawl all available pages.
        """
        if self._discover_entries_override is not None:
            return await self._discover_entries_override(fetch_historical)

        max_pages = None if fetch_historical else self.max_discovery_pages
        return await self._discover_index_entries(max_pages=max_pages)

    @staticmethod
    def _extract_reference(*candidates: str | None) -> str | None:
        for candidate in candidates:
            if candidate is None:
                continue
            match = CERTFR_REFERENCE_RE.search(candidate)
            if match is not None:
                return match.group(1).upper()
        return None

    async def _discover_index_entries(
        self,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        """Crawl the paginated /cti/ and /ioc/ indexes to find reports.

        Args:
            max_pages: Maximum pages to crawl per base URL.  ``None`` means
                unlimited (full backfill).  Default ``None`` (set by caller
                via ``max_discovery_pages``).
        """
        from urllib.parse import urljoin

        from bs4 import BeautifulSoup

        entries: list[dict[str, Any]] = []
        base_urls = [
            "https://www.cert.ssi.gouv.fr/cti/",
            "https://www.cert.ssi.gouv.fr/ioc/",
        ]

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
        ) as client:
            for base_url in base_urls:
                page = 1
                while True:
                    url = base_url if page == 1 else f"{base_url}page/{page}/"
                    response = await client.get(url)
                    if response.status_code == 404:
                        break
                    response.raise_for_status()

                    soup = BeautifulSoup(response.text, "html.parser")
                    articles = soup.select("article.cert-alert, article.item")
                    if not articles:
                        articles = soup.find_all(
                            "a", href=re.compile(r"/cti/CERTFR|/ioc/CERTFR")
                        )

                    if not articles:
                        break

                    found_any = False
                    for article in articles:
                        link_tag = article if article.name == "a" else article.find("a")
                        if not link_tag or not link_tag.get("href"):
                            continue

                        href = urljoin(
                            "https://www.cert.ssi.gouv.fr",
                            str(link_tag.get("href", "")),
                        )
                        title = link_tag.get_text(strip=True)
                        reference = self._extract_reference(href, title)
                        if not reference:
                            continue

                        date_tag = article.find("time") if article.name != "a" else None
                        published = date_tag.get("datetime", "") if date_tag else None

                        entries.append(
                            {
                                "title": title,
                                "link": href,
                                "reference": reference,
                                "published": published,
                                "summary": None,
                            }
                        )
                        found_any = True

                    if not found_any:
                        break

                    page += 1
                    if max_pages is not None and page > max_pages:
                        break
                    if self.delay_between_requests > 0:
                        await asyncio.sleep(self.delay_between_requests)

        return entries

    # ------------------------------------------------------------------
    # Content extraction
    # ------------------------------------------------------------------

    async def _extract_report(
        self,
        entry: dict[str, Any],
    ) -> ExtractedContent:
        reference: str = entry["reference"]
        title: str = entry.get("title") or reference
        link: str | None = entry.get("link")

        # Try PDF first
        pdf_bytes = await self._download_pdf(reference)
        if pdf_bytes is not None:
            text = await asyncio.to_thread(
                self._extract_text_from_pdf,
                pdf_bytes,
            )
            method = "pdfplumber"
            source_url = f"{self.pdf_base_url}/{reference}.pdf"
        elif link:
            # No PDF available — expected for some newer reports.
            # Fall back to scraping the web page.
            html = await self._download_html(link)
            text = self._extract_text_from_html(html)
            method = "html_scraping"
            source_url = link
        else:
            raise ValueError(f"{reference}: no PDF available and no page link in feed")

        if not text or len(text.strip()) < 50:
            raise ValueError(
                f"{reference}: extracted text too short "
                f"({len(text.strip()) if text else 0} chars)"
            )

        iocs = self._extract_iocs(text)
        is_phishing = self._classify_phishing_relevance(text, title)

        return ExtractedContent(
            reference=reference,
            title=title,
            text=text,
            text_length=len(text),
            extraction_method=method,
            source_url=source_url,
            domains=iocs["domains"],
            emails=iocs["emails"],
            ips=iocs["ips"],
            hashes=iocs["hashes"],
            is_phishing_related=is_phishing,
        )

    async def _download_pdf(self, reference: str) -> bytes | None:
        """Attempt to download the PDF.  Returns ``None`` when the PDF
        does not exist (HTTP 404) — this is normal for some reports."""
        url = f"{self.pdf_base_url}/{reference}.pdf"
        try:
            response = await self._http_get(url)
            if response.status_code == 404:
                return None  # not an error — PDF not published
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "pdf" not in content_type and "octet" not in content_type:
                return None  # not actually a PDF (redirect to error page)
            return response.content
        except httpx.HTTPStatusError:
            return None  # treat other HTTP errors as "no PDF available"
        except httpx.RequestError:
            return None  # network issues — still not a fatal error

    async def _download_html(self, url: str) -> str:
        response = await self._http_get(url)
        response.raise_for_status()
        return response.text

    async def _http_get(self, url: str) -> httpx.Response:
        if self._download_url is not None:
            return await self._download_url(url)
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
        ) as client:
            return await client.get(url)

    # ------------------------------------------------------------------
    # Text extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
        import pdfplumber

        text_parts: list[str] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n\n".join(text_parts)

    @staticmethod
    def _extract_text_from_html(html: str) -> str:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        article = soup.select_one("article.article")
        if article is not None:
            return article.get_text(separator="\n", strip=True)
        # Broader fallback — try main content area
        main = soup.select_one("main") or soup.select_one(".content")
        if main is not None:
            return main.get_text(separator="\n", strip=True)
        return soup.get_text(separator="\n", strip=True)

    # ------------------------------------------------------------------
    # IOC extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_iocs(text: str) -> dict[str, list[str]]:
        domains = sorted(
            {
                m.group(0).lower()
                for m in _DOMAIN_RE.finditer(text)
                if m.group(0).lower() not in _NOISE_DOMAINS
            }
        )
        emails = sorted({m.group(0).lower() for m in _EMAIL_RE.finditer(text)})
        ips = sorted(
            {
                m.group(0)
                for m in _IPV4_RE.finditer(text)
                if not m.group(0).startswith(("0.", "127.", "10.", "192.168."))
            }
        )
        raw_hashes = sorted({m.group(0).lower() for m in _HASH_RE.finditer(text)})
        # Only keep hashes that are exactly 32, 40, or 64 hex chars
        hashes = [h for h in raw_hashes if len(h) in (32, 40, 64)]

        return {
            "domains": domains,
            "emails": emails,
            "ips": ips,
            "hashes": hashes,
        }

    @staticmethod
    def _classify_phishing_relevance(text: str, title: str) -> bool:
        combined = f"{title} {text}".lower()
        return any(kw in combined for kw in _PHISHING_KEYWORDS)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _persist_content(
        self,
        session: AsyncSession,
        *,
        ingestion_run: DataIngestionRun,
        source_system: DataSourceSystem,
        content: ExtractedContent,
        collected_at: datetime,
    ) -> tuple[DataRawObject, DataRawRecord]:
        # Store the raw content (PDF bytes or HTML) as a snapshot
        snapshot_payload = content.text.encode("utf-8")
        ext = "pdf.txt" if content.extraction_method == "pdfplumber" else "html.txt"
        object_key = self.snapshot_store.build_object_key(
            source_prefix=self.snapshot_prefix,
            filename=f"{content.reference}.{ext}",
        )
        snapshot_result = await self.snapshot_store.write_snapshot(
            object_key=object_key,
            payload=snapshot_payload,
            content_type="text/plain; charset=utf-8",
        )

        object_type = (
            ObjectType.PDF_DOCUMENT
            if content.extraction_method == "pdfplumber"
            else ObjectType.HTML_PAGE
        )
        raw_object = DataRawObject(
            ingestion_run_id=ingestion_run.id,
            external_ref=f"cert-fr#content#{content.reference}",
            object_type=object_type,
            storage_uri=snapshot_result.storage_uri,
            source_format=content.extraction_method,
            content_hash=snapshot_result.content_hash,
            size_bytes=snapshot_result.size_bytes,
            source_metadata={
                "source_name": source_system.name,
                "reference": content.reference,
                "title": content.title,
                "source_url": content.source_url,
                "extraction_method": content.extraction_method,
                "is_phishing_related": content.is_phishing_related,
                "ioc_counts": {
                    "domains": len(content.domains),
                    "emails": len(content.emails),
                    "ips": len(content.ips),
                    "hashes": len(content.hashes),
                },
            },
            collected_at=collected_at,
        )
        session.add(raw_object)
        await session.flush()

        enriched_content = json.dumps(
            {
                "reference": content.reference,
                "title": content.title,
                "text": content.text,
                "text_length": content.text_length,
                "extraction_method": content.extraction_method,
                "source_url": content.source_url,
                "domains": content.domains,
                "emails": content.emails,
                "ips": content.ips,
                "hashes": content.hashes,
                "is_phishing_related": content.is_phishing_related,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        raw_record = DataRawRecord(
            raw_object_id=raw_object.id,
            source_system_id=source_system.id,
            record_key=content.reference,
            raw_content=enriched_content,
            detected_language="fr",
            is_usable=True,
            rejection_reason=None,
            extracted_at=datetime.now(timezone.utc),
        )
        session.add(raw_record)
        await session.flush()

        return raw_object, raw_record

    async def _existing_references(
        self,
        session: AsyncSession,
    ) -> set[str]:
        """Return references already content-extracted."""
        stmt = select(DataRawObject.external_ref).where(
            DataRawObject.external_ref.like("cert-fr#content#%"),
        )
        rows = await session.scalars(stmt)
        refs: set[str] = set()
        for ext_ref in rows:
            if ext_ref and ext_ref.startswith("cert-fr#content#"):
                refs.add(ext_ref.removeprefix("cert-fr#content#"))
        return refs

    async def _get_or_create_source(
        self,
        session: AsyncSession,
    ) -> DataSourceSystem:
        source = await self.source_repository.get_by_name(
            session,
            self.source_name,
        )
        if source is not None:
            return source
        return await self.source_service.create(
            session,
            DataSourceCreate(
                name=self.source_name,
                source_type=SourceType.SCRAPING,
                description=("CERT-FR CTI reports — bi-weekly PDF extraction"),
                owner_name="ANSSI",
                legal_basis="public_threat_intel",
                contains_personal_data=False,
                retention_days=365,
            ),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _finish_run(
        self,
        ingestion_run: DataIngestionRun,
        status: IngestionStatus,
        result: CertFRCtiResult,
    ) -> None:
        ingestion_run.finished_at = datetime.now(timezone.utc)
        ingestion_run.status = status
        ingestion_run.raw_object_count = result.extracted_count
        ingestion_run.raw_record_count = result.extracted_count
        ingestion_run.log_message = result.log_message

    @staticmethod
    def _build_summary(result: CertFRCtiResult) -> str:
        parts: list[str] = [
            f"CERT-FR CTI extraction: "
            f"{result.discovered_count} discovered, "
            f"{result.skipped_count} already extracted, "
            f"{result.new_count} new, "
            f"{result.extracted_count} extracted",
        ]
        if result.failed_count:
            parts.append(f", {result.failed_count} failed")
        return "".join(parts)
