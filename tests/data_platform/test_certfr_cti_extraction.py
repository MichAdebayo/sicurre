"""Tests for the single-pass CERT-FR CTI content extraction service."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from core.database import Base
from db.models import (
    DataIngestionRun,
    DataRawObject,
    DataRawRecord,
)
from data_platform.extractors.certfr_cti import (
    CertFRCtiExtractor,
    ExtractedContent,
)
from data_platform.services.snapshot_storage import (
    LocalSnapshotStore,
    SnapshotWriteResult,
)


def _mock_response(
    status_code: int = 200,
    *,
    content: bytes | None = None,
    text: str | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Build an ``httpx.Response`` with a dummy request attached.

    ``httpx.Response.raise_for_status`` requires ``self.request`` to be
    set; constructing a response without one causes a crash.
    """
    kwargs: dict[str, object] = {"status_code": status_code}
    if content is not None:
        kwargs["content"] = content
    if text is not None:
        kwargs["text"] = text
    if headers:
        kwargs["headers"] = headers
    resp = httpx.Response(**kwargs)  # type: ignore[arg-type]
    resp.request = httpx.Request("GET", "https://mock")
    return resp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CTI_ENTRIES = [
    {
        "title": "Opération ENDGAME de novembre 2025",
        "link": "https://www.cert.ssi.gouv.fr/cti/CERTFR-2025-CTI-011/",
        "guid": "https://www.cert.ssi.gouv.fr/cti/CERTFR-2025-CTI-011/",
        "reference": "CERTFR-2025-CTI-011",
        "published": "Thu, 13 Nov 2025 00:00:00 +0000",
        "summary": "Opération ENDGAME de novembre 2025",
    },
    {
        "title": "Panorama de la cybermenace 2024",
        "link": "https://www.cert.ssi.gouv.fr/cti/CERTFR-2025-CTI-003/",
        "guid": "https://www.cert.ssi.gouv.fr/cti/CERTFR-2025-CTI-003/",
        "reference": "CERTFR-2025-CTI-003",
        "published": "Tue, 11 Mar 2025 00:00:00 +0000",
        "summary": "Panorama de la cybermenace 2024",
    },
]

SAMPLE_PDF_TEXT = (
    "Rapport menaces et incidents du CERT-FR\n"
    "VenomRAT est un programme malveillant d'accès à distance vendu en tant "
    "que Malware-as-a-Service (MaaS). Ce code est principalement diffusé via "
    "des campagnes d'hameçonnage ciblant des entités françaises.\n"
    "Indicateurs de compromission:\n"
    "- Domaine: evil-phishing.fr\n"
    "- Email: attacker@malware-domain.net\n"
    "- IP: 203.0.113.42\n"
    "- Hash: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4\n"
)

SAMPLE_HTML_PAGE = """
<!DOCTYPE html>
<html>
<body>
<article class="article">
    <h1>Panorama de la cybermenace 2024</h1>
    <p>Dans cette quatrième édition du panorama de la menace,
    l'Agence nationale de la sécurité des systèmes d'information (ANSSI)
    revient sur les grandes tendances de la menace informatique.</p>
    <p>Les attaques par rançongiciel et les campagnes d'hameçonnage
    continuent de cibler les entreprises françaises.</p>
</article>
</body>
</html>
"""

SAMPLE_HTML_NO_PHISHING = """
<!DOCTYPE html>
<html>
<body>
<article class="article">
    <h1>Secteur du cloud - État de la menace informatique</h1>
    <p>Le Cloud computing, devenu incontournable pour les secteurs
    public et privé, favorise la transformation numérique mais offre
    également de nouvelles opportunités d'attaques.</p>
    <p>Sécurité et infrastructure réseau dans un contexte professionnel.</p>
</article>
</body>
</html>
"""


class RecordingSnapshotStore:
    """In-memory snapshot store for tests."""

    def __init__(self) -> None:
        self.snapshots: dict[str, bytes] = {}

    def build_object_key(self, *, source_prefix: str, filename: str) -> str:
        return f"raw-snapshots/{source_prefix}/{filename}"

    async def write_snapshot(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str,
    ) -> SnapshotWriteResult:
        self.snapshots[object_key] = payload
        return SnapshotWriteResult(
            storage_uri=f"r2://sicurre-raw/{object_key}",
            content_hash="test-hash",
            size_bytes=len(payload),
            local_path=None,
        )


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession,
    )
    try:
        yield factory
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Unit tests — text extraction
# ---------------------------------------------------------------------------


def test_extract_text_from_html() -> None:
    text = CertFRCtiExtractor._extract_text_from_html(SAMPLE_HTML_PAGE)

    assert "Panorama de la cybermenace 2024" in text
    assert "ANSSI" in text
    assert "hameçonnage" in text


def test_extract_text_from_html_fallback_main() -> None:
    html = """
    <html><body>
    <main><p>Contenu principal du rapport CERT-FR.</p></main>
    </body></html>
    """
    text = CertFRCtiExtractor._extract_text_from_html(html)
    assert "Contenu principal" in text


def test_extract_text_from_html_fallback_body() -> None:
    html = "<html><body><p>Texte brut sans article ni main.</p></body></html>"
    text = CertFRCtiExtractor._extract_text_from_html(html)
    assert "Texte brut" in text


# ---------------------------------------------------------------------------
# Unit tests — IOC extraction
# ---------------------------------------------------------------------------


def test_extract_iocs_finds_domains() -> None:
    text = "Le domaine evil-phishing.fr est utilisé pour l'attaque."
    iocs = CertFRCtiExtractor._extract_iocs(text)
    assert "evil-phishing.fr" in iocs["domains"]


def test_extract_iocs_filters_noise_domains() -> None:
    text = "Voir https://cert.ssi.gouv.fr pour plus d'informations."
    iocs = CertFRCtiExtractor._extract_iocs(text)
    assert "cert.ssi.gouv.fr" not in iocs["domains"]


def test_extract_iocs_finds_emails() -> None:
    text = "Contacter attacker@malware-domain.net pour les détails."
    iocs = CertFRCtiExtractor._extract_iocs(text)
    assert "attacker@malware-domain.net" in iocs["emails"]


def test_extract_iocs_finds_ipv4() -> None:
    text = "L'adresse IP du C2 est 203.0.113.42."
    iocs = CertFRCtiExtractor._extract_iocs(text)
    assert "203.0.113.42" in iocs["ips"]


def test_extract_iocs_filters_private_ips() -> None:
    text = "Le serveur local 192.168.1.1 et 10.0.0.1 et 127.0.0.1."
    iocs = CertFRCtiExtractor._extract_iocs(text)
    assert len(iocs["ips"]) == 0


def test_extract_iocs_finds_md5_hash() -> None:
    text = "Hash: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
    iocs = CertFRCtiExtractor._extract_iocs(text)
    assert "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4" in iocs["hashes"]


def test_extract_iocs_finds_sha256_hash() -> None:
    h = "a" * 64
    text = f"SHA-256: {h}"
    iocs = CertFRCtiExtractor._extract_iocs(text)
    assert h in iocs["hashes"]


def test_extract_iocs_rejects_wrong_length_hex() -> None:
    text = "Not a hash: abcdef1234567890abcdef12345"  # 29 chars
    iocs = CertFRCtiExtractor._extract_iocs(text)
    assert len(iocs["hashes"]) == 0


# ---------------------------------------------------------------------------
# Unit tests — phishing classification
# ---------------------------------------------------------------------------


def test_classify_phishing_positive() -> None:
    assert CertFRCtiExtractor._classify_phishing_relevance(
        "campagne d'hameçonnage ciblant la France", "Alerte phishing"
    )


def test_classify_phishing_negative() -> None:
    assert not CertFRCtiExtractor._classify_phishing_relevance(
        "Vulnérabilité dans OpenSSL corrigée.", "Avis de sécurité"
    )


def test_classify_phishing_via_ransomware_keyword() -> None:
    assert CertFRCtiExtractor._classify_phishing_relevance(
        "Attaque par rançongiciel contre un hôpital.", "Alerte rançongiciel"
    )


# ---------------------------------------------------------------------------
# Unit tests — RSS feed parsing
# ---------------------------------------------------------------------------


def test_parse_feed_extracts_cti_references() -> None:
    payload = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>CERT-FR CTI</title>
    <item>
      <title>Panorama de la cybermenace 2024</title>
      <link>https://www.cert.ssi.gouv.fr/cti/CERTFR-2025-CTI-003/</link>
      <guid>https://www.cert.ssi.gouv.fr/cti/CERTFR-2025-CTI-003/</guid>
      <pubDate>Tue, 11 Mar 2025 00:00:00 +0000</pubDate>
      <description>Panorama annuel.</description>
    </item>
    <item>
      <title>Not a CTI entry</title>
      <link>https://www.cert.ssi.gouv.fr/avis/CERTFR-2025-AVI-001/</link>
      <guid>https://www.cert.ssi.gouv.fr/avis/CERTFR-2025-AVI-001/</guid>
    </item>
  </channel>
</rss>
"""
    entries = CertFRCtiExtractor._parse_feed(payload)

    # Only the CTI entry should be returned (AVI is filtered by regex)
    assert len(entries) == 1
    assert entries[0]["reference"] == "CERTFR-2025-CTI-003"
    assert entries[0]["title"] == "Panorama de la cybermenace 2024"


# ---------------------------------------------------------------------------
# Integration tests — full extraction flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extraction_with_pdf_creates_lineage(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """PDF available → pdfplumber extraction → persists full lineage."""

    async def fetch_feed() -> list[dict[str, object]]:
        return [SAMPLE_CTI_ENTRIES[0]]

    async def download_url(url: str) -> httpx.Response:
        # Simulate PDF endpoint returning text (pdfplumber needs real
        # PDF bytes; we mock extract_text_from_pdf instead)
        if url.endswith(".pdf"):
            return _mock_response(
                200,
                content=b"fake-pdf-bytes",
                headers={"content-type": "application/pdf"},
            )
        raise httpx.RequestError("unexpected URL")

    store = RecordingSnapshotStore()
    extractor = CertFRCtiExtractor(
        fetch_feed=fetch_feed,
        download_url=download_url,
        snapshot_store=store,
        delay_between_requests=0,
    )

    # Monkey-patch PDF extraction to avoid needing real PDF bytes
    original_extract = CertFRCtiExtractor._extract_text_from_pdf

    @staticmethod  # type: ignore[misc]
    def mock_extract(pdf_bytes: bytes) -> str:
        return SAMPLE_PDF_TEXT

    CertFRCtiExtractor._extract_text_from_pdf = mock_extract  # type: ignore[assignment]

    try:
        async with session_factory() as session:
            result = await extractor.run(
                session,
                trigger_mode="scheduled",
                started_at=datetime(2026, 3, 26, 8, 0, tzinfo=timezone.utc),
            )

            ingestion_run = await session.scalar(select(DataIngestionRun))
            raw_object = await session.scalar(select(DataRawObject))
            raw_records = list(
                (await session.scalars(select(DataRawRecord))).all()
            )
    finally:
        CertFRCtiExtractor._extract_text_from_pdf = original_extract  # type: ignore[assignment]

    # Result assertions
    assert result.discovered_count == 1
    assert result.new_count == 1
    assert result.extracted_count == 1
    assert result.skipped_count == 0
    assert result.failed_count == 0
    assert len(result.reports) == 1
    assert result.reports[0].extraction_method == "pdfplumber"
    assert result.reports[0].is_phishing_related is True  # "hameçonnage" in text

    # Lineage assertions
    assert ingestion_run is not None
    assert ingestion_run.status == "completed"
    assert ingestion_run.trigger_mode == "scheduled"
    assert raw_object is not None
    assert raw_object.object_type == "pdf_document"
    assert raw_object.external_ref == "cert-fr#content#CERTFR-2025-CTI-011"
    assert raw_object.source_metadata["extraction_method"] == "pdfplumber"
    assert len(raw_records) == 1
    assert raw_records[0].record_key == "CERTFR-2025-CTI-011"
    assert raw_records[0].detected_language == "fr"

    # Verify enriched content in raw_content
    content = json.loads(raw_records[0].raw_content)
    assert content["extraction_method"] == "pdfplumber"
    assert content["is_phishing_related"] is True
    assert "evil-phishing.fr" in content["domains"]
    assert "attacker@malware-domain.net" in content["emails"]
    assert "203.0.113.42" in content["ips"]
    assert "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4" in content["hashes"]


@pytest.mark.asyncio
async def test_extraction_html_fallback_when_no_pdf(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """No PDF (404) → HTML scraping fallback → not treated as error."""

    async def fetch_feed() -> list[dict[str, object]]:
        return [SAMPLE_CTI_ENTRIES[1]]

    async def download_url(url: str) -> httpx.Response:
        if url.endswith(".pdf"):
            return _mock_response(404)  # no PDF — expected
        if "CERTFR-2025-CTI-003" in url:
            return _mock_response(200, text=SAMPLE_HTML_PAGE)
        raise httpx.RequestError("unexpected URL")

    store = RecordingSnapshotStore()
    extractor = CertFRCtiExtractor(
        fetch_feed=fetch_feed,
        download_url=download_url,
        snapshot_store=store,
        delay_between_requests=0,
    )

    async with session_factory() as session:
        result = await extractor.run(session, trigger_mode="scheduled")

        raw_object = await session.scalar(select(DataRawObject))
        raw_records = list(
            (await session.scalars(select(DataRawRecord))).all()
        )

    # Should succeed without any failures
    assert result.extracted_count == 1
    assert result.failed_count == 0
    assert result.reports[0].extraction_method == "html_scraping"

    # Object type should be HTML, not PDF
    assert raw_object is not None
    assert raw_object.object_type == "html_page"
    assert raw_object.source_metadata["extraction_method"] == "html_scraping"

    content = json.loads(raw_records[0].raw_content)
    assert content["extraction_method"] == "html_scraping"
    assert "ANSSI" in content["text"]


@pytest.mark.asyncio
async def test_extraction_skips_already_extracted(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Reports already extracted are skipped — no duplicate processing."""
    call_count = 0

    async def fetch_feed() -> list[dict[str, object]]:
        return [SAMPLE_CTI_ENTRIES[0]]

    async def download_url(url: str) -> httpx.Response:
        nonlocal call_count
        if url.endswith(".pdf"):
            call_count += 1
            return _mock_response(
                200,
                content=b"fake-pdf",
                headers={"content-type": "application/pdf"},
            )
        raise httpx.RequestError("unexpected URL")

    store = RecordingSnapshotStore()
    extractor = CertFRCtiExtractor(
        fetch_feed=fetch_feed,
        download_url=download_url,
        snapshot_store=store,
        delay_between_requests=0,
    )

    original = CertFRCtiExtractor._extract_text_from_pdf

    @staticmethod  # type: ignore[misc]
    def mock_extract(pdf_bytes: bytes) -> str:
        return SAMPLE_PDF_TEXT

    CertFRCtiExtractor._extract_text_from_pdf = mock_extract  # type: ignore[assignment]

    try:
        # First run — should extract
        async with session_factory() as session:
            result1 = await extractor.run(session, trigger_mode="scheduled")

        assert result1.extracted_count == 1
        assert call_count == 1

        # Second run — should skip (already extracted)
        async with session_factory() as session:
            result2 = await extractor.run(session, trigger_mode="scheduled")

        assert result2.extracted_count == 0
        assert result2.skipped_count == 1
        assert result2.new_count == 0
        assert call_count == 1  # no additional HTTP calls
    finally:
        CertFRCtiExtractor._extract_text_from_pdf = original  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_extraction_no_entries_in_feed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Empty feed → completed with zero counts, not an error."""

    async def fetch_feed() -> list[dict[str, object]]:
        return []

    store = RecordingSnapshotStore()
    extractor = CertFRCtiExtractor(
        fetch_feed=fetch_feed,
        snapshot_store=store,
        delay_between_requests=0,
    )

    async with session_factory() as session:
        result = await extractor.run(session, trigger_mode="scheduled")
        ingestion_run = await session.scalar(select(DataIngestionRun))

    assert result.discovered_count == 0
    assert result.extracted_count == 0
    assert result.failed_count == 0
    assert "No CTI entries found" in result.log_message
    assert ingestion_run is not None
    assert ingestion_run.status == "completed"


@pytest.mark.asyncio
async def test_extraction_partial_failure(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """One report succeeds, one fails → status is 'partial'."""

    async def fetch_feed() -> list[dict[str, object]]:
        return list(SAMPLE_CTI_ENTRIES)

    async def download_url(url: str) -> httpx.Response:
        if "CERTFR-2025-CTI-011" in url and url.endswith(".pdf"):
            return _mock_response(404)
        if "CERTFR-2025-CTI-011" in url:
            return _mock_response(200, text=SAMPLE_HTML_PAGE)
        if "CERTFR-2025-CTI-003" in url:
            # Both PDF and HTML fail
            raise httpx.RequestError("network down")
        raise httpx.RequestError("unexpected URL")

    store = RecordingSnapshotStore()
    extractor = CertFRCtiExtractor(
        fetch_feed=fetch_feed,
        download_url=download_url,
        snapshot_store=store,
        delay_between_requests=0,
    )

    async with session_factory() as session:
        result = await extractor.run(session, trigger_mode="scheduled")
        ingestion_run = await session.scalar(select(DataIngestionRun))

    assert result.extracted_count == 1
    assert result.failed_count == 1
    assert ingestion_run is not None
    assert ingestion_run.status == "partial"


@pytest.mark.asyncio
async def test_extraction_with_local_snapshot_store(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path,
) -> None:
    """Verify PDF text is stored as a local file snapshot."""

    async def fetch_feed() -> list[dict[str, object]]:
        return [SAMPLE_CTI_ENTRIES[0]]

    async def download_url(url: str) -> httpx.Response:
        if url.endswith(".pdf"):
            return _mock_response(
                200,
                content=b"fake-pdf",
                headers={"content-type": "application/pdf"},
            )
        raise httpx.RequestError("unexpected URL")

    local_store = LocalSnapshotStore(root_dir=tmp_path, repo_root=tmp_path)
    extractor = CertFRCtiExtractor(
        fetch_feed=fetch_feed,
        download_url=download_url,
        snapshot_dir=tmp_path,
        snapshot_store=local_store,
        delay_between_requests=0,
    )

    original = CertFRCtiExtractor._extract_text_from_pdf

    @staticmethod  # type: ignore[misc]
    def mock_extract(pdf_bytes: bytes) -> str:
        return SAMPLE_PDF_TEXT

    CertFRCtiExtractor._extract_text_from_pdf = mock_extract  # type: ignore[assignment]

    try:
        async with session_factory() as session:
            result = await extractor.run(session, trigger_mode="manual")

        assert result.extracted_count == 1
        # Check snapshot file was created
        snapshot_files = list(tmp_path.rglob("*.txt"))
        assert len(snapshot_files) == 1
        assert "CERTFR-2025-CTI-011" in snapshot_files[0].name
    finally:
        CertFRCtiExtractor._extract_text_from_pdf = original  # type: ignore[assignment]
