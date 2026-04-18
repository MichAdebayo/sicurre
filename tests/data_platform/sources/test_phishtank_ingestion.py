"""Tests for the PhishTank ingestion service."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

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
from data_platform.extractors.phishtank import (
    PhishTankFetchedPayload,
    PhishTankFeedClient,
    PhishTankIngestionService,
)
from data_platform.services.shared.snapshot_storage import (
    LocalSnapshotStore,
    SnapshotWriteResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class RecordingSnapshotStore:
    def __init__(self) -> None:
        self.object_key: str | None = None

    def build_object_key(self, *, source_prefix: str, filename: str) -> str:
        return f"raw-snapshots/{source_prefix}/{filename}"

    async def write_snapshot(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str,
    ) -> SnapshotWriteResult:
        self.object_key = object_key
        return SnapshotWriteResult(
            storage_uri=f"r2://sicurre-raw/{object_key}",
            content_hash="hash",
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
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    try:
        yield factory
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Unit tests — PhishTankFeedClient
# ---------------------------------------------------------------------------


def test_feed_url_without_api_key() -> None:
    client = PhishTankFeedClient()
    assert client.feed_url == ("https://data.phishtank.com/data/online-valid.csv")


def test_feed_url_with_api_key() -> None:
    client = PhishTankFeedClient(api_key="my-secret-key")
    assert client.feed_url == (
        "https://data.phishtank.com/data/my-secret-key/online-valid.csv"
    )


def test_feed_url_custom_base_with_key() -> None:
    client = PhishTankFeedClient(
        feed_url="https://example.com/feed.csv",
        api_key="abc123",
    )
    assert client.feed_url == "https://example.com/abc123/feed.csv"


def test_retryable_response_detects_transient_cdn_404() -> None:
    client = PhishTankFeedClient()
    redirect_request = httpx.Request(
        "GET", "https://data.phishtank.com/data/online-valid.csv"
    )
    redirect_response = httpx.Response(
        302,
        request=redirect_request,
        headers={"location": "https://cdn.phishtank.com/datadumps/verified_online.csv"},
    )
    final_request = httpx.Request(
        "GET",
        "https://cdn.phishtank.com/datadumps/verified_online.csv",
    )
    final_response = httpx.Response(
        404,
        request=final_request,
        history=[redirect_response],
    )

    assert client._should_retry_response(final_response) is True


def test_retryable_response_does_not_retry_plain_404() -> None:
    client = PhishTankFeedClient()
    response = httpx.Response(
        404,
        request=httpx.Request(
            "GET", "https://data.phishtank.com/data/online-valid.csv"
        ),
    )

    assert client._should_retry_response(response) is False


# ---------------------------------------------------------------------------
# Unit tests — French filtering
# ---------------------------------------------------------------------------


def test_is_french_target_fr_tld() -> None:
    svc = PhishTankIngestionService.__new__(PhishTankIngestionService)
    assert svc._is_french_target("https://impots-verification.gouv.fr/login")
    assert svc._is_french_target("https://example.fr/phish")
    assert svc._is_french_target("https://sub.domain.fr:8080/path")


def test_is_french_target_brand_keyword() -> None:
    svc = PhishTankIngestionService.__new__(PhishTankIngestionService)
    assert svc._is_french_target("https://evil.com/ameli-remboursement")
    assert svc._is_french_target("https://evil.com/bnpparibas-login")
    assert svc._is_french_target("https://evil.com/chronopost-livraison")


def test_is_french_target_rejects_non_french() -> None:
    svc = PhishTankIngestionService.__new__(PhishTankIngestionService)
    assert not svc._is_french_target("https://paypal.com/login")
    assert not svc._is_french_target("https://wells-fargo.com/signin")
    assert not svc._is_french_target("https://example.de/phish")


def test_french_filter_reason() -> None:
    svc = PhishTankIngestionService.__new__(PhishTankIngestionService)
    assert svc._french_filter_reason("https://evil.fr/page") == "fr_tld"
    assert svc._french_filter_reason("https://evil.com/urssaf") == "brand:urssaf"


def test_parse_domain() -> None:
    svc = PhishTankIngestionService.__new__(PhishTankIngestionService)
    assert svc._parse_domain("https://evil.example.fr/path") == "evil.example.fr"
    assert svc._parse_domain("not-a-url") == ""


# ---------------------------------------------------------------------------
# Integration tests — full ingestion flow with French filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phishtank_ingestion_filters_french_only(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Only French-targeted entries should be ingested."""
    entries = [
        {"phish_id": "1001", "url": "https://secure-urssaf.example.fr/login"},
        {"phish_id": "1002", "url": "https://paypal.com/login"},  # non-French
        {"phish_id": "1003", "url": "https://evil.com/ameli-remboursement"},
        {"phish_id": "1004", "url": "https://wellsfargo.com/signin"},  # non-French
    ]

    async def fetch_entries() -> list[dict[str, str]]:
        return entries

    store = RecordingSnapshotStore()
    service = PhishTankIngestionService(
        fetch_entries=fetch_entries,
        snapshot_store=store,
    )

    async with session_factory() as session:
        result = await service.run(session, trigger_mode="manual")
        records = list((await session.scalars(select(DataRawRecord))).all())

    assert result.total_feed_count == 4
    assert result.filtered_count == 2  # paypal + wellsfargo
    assert result.raw_record_count == 2  # urssaf.fr + ameli
    assert result.skipped_count == 0
    assert {r.record_key for r in records} == {"1001", "1003"}

    # Verify enrichment in raw_content
    for record in records:
        content = json.loads(record.raw_content)
        assert content["label"] == "phishing"
        assert content["source"] == "phishtank_api"
        assert "domain" in content
        assert "filter_reason" in content


@pytest.mark.asyncio
async def test_phishtank_ingestion_persists_lineage(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path,
) -> None:
    entries = [
        {
            "phish_id": "2001",
            "url": "https://secure-urssaf-fr.example.fr/login",
            "verified": "yes",
        },
        {
            "phish_id": "2002",
            "url": "https://ameli-verification.example/update",
            "verified": "yes",
        },
    ]

    async def fetch_entries() -> list[dict[str, str]]:
        return entries

    local_store = LocalSnapshotStore(root_dir=tmp_path, repo_root=tmp_path)

    service = PhishTankIngestionService(
        fetch_entries=fetch_entries,
        snapshot_dir=tmp_path,
        snapshot_store=local_store,
    )

    async with session_factory() as session:
        result = await service.run(
            session,
            trigger_mode="manual",
            started_at=datetime(2026, 3, 25, 8, 0, tzinfo=timezone.utc),
        )

        ingestion_run = await session.scalar(select(DataIngestionRun))
        raw_object = await session.scalar(select(DataRawObject))
        raw_records = list((await session.scalars(select(DataRawRecord))).all())

    assert result.raw_object_count == 1
    assert result.raw_record_count == 2
    assert result.skipped_count == 0
    assert result.snapshot_path is not None
    assert result.snapshot_path.exists()
    assert result.snapshot_storage_uri.endswith(".csv")
    assert ingestion_run is not None
    assert ingestion_run.status == "completed"
    assert ingestion_run.raw_object_count == 1
    assert ingestion_run.raw_record_count == 2
    assert raw_object is not None
    assert raw_object.object_type == "api_payload"
    assert raw_object.source_format == "csv"
    assert len(raw_records) == 2
    assert (
        result.snapshot_path.read_text(encoding="utf-8")
        .splitlines()[0]
        .startswith("phish_id,url,phish_detail_url")
    )


@pytest.mark.asyncio
async def test_phishtank_ingestion_preserves_fetched_csv_payload(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    raw_csv = (
        "phish_id,url,phish_detail_url,submission_time,verified,verification_time,online,target\n"
        "7001,https://secure-urssaf.example.fr/login,,,yes,,yes,URSSAF\n"
    ).encode("utf-8")

    async def fetch_entries() -> PhishTankFetchedPayload:
        return PhishTankFetchedPayload(
            entries=[
                {
                    "phish_id": "7001",
                    "url": "https://secure-urssaf.example.fr/login",
                    "target": "URSSAF",
                }
            ],
            snapshot_bytes=raw_csv,
            source_url="https://cdn.phishtank.example/verified_online.csv",
        )

    local_store = LocalSnapshotStore(root_dir=tmp_path, repo_root=tmp_path)
    service = PhishTankIngestionService(
        fetch_entries=fetch_entries,
        snapshot_dir=tmp_path,
        snapshot_store=local_store,
    )

    async with session_factory() as session:
        result = await service.run(session, trigger_mode="manual")

    assert result.snapshot_path is not None
    assert result.snapshot_path.read_bytes() == raw_csv


@pytest.mark.asyncio
async def test_phishtank_ingestion_marks_failed_runs(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path,
) -> None:
    async def fetch_entries() -> list[dict[str, str]]:
        raise RuntimeError("feed unavailable")

    local_store = LocalSnapshotStore(root_dir=tmp_path, repo_root=tmp_path)

    service = PhishTankIngestionService(
        fetch_entries=fetch_entries,
        snapshot_dir=tmp_path,
        snapshot_store=local_store,
    )

    async with session_factory() as session:
        with pytest.raises(RuntimeError, match="feed unavailable"):
            await service.run(session, trigger_mode="scheduled")

        ingestion_run = await session.scalar(select(DataIngestionRun))

    assert ingestion_run is not None
    assert ingestion_run.status == "failed"


# ---------------------------------------------------------------------------
# Tests — Deduplication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phishtank_dedup_skips_already_ingested(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Second run with same entries → all skipped, zero new records."""
    entries = [
        {"phish_id": "3001", "url": "https://fake-banque.example.fr/connecter"},
        {"phish_id": "3002", "url": "https://faux-impots.example.fr/verifier"},
    ]

    async def fetch_entries() -> list[dict[str, str]]:
        return entries

    store = RecordingSnapshotStore()
    service = PhishTankIngestionService(
        fetch_entries=fetch_entries,
        snapshot_store=store,
    )

    async with session_factory() as session:
        result1 = await service.run(session, trigger_mode="manual")

    assert result1.raw_record_count == 2

    async with session_factory() as session:
        result2 = await service.run(session, trigger_mode="scheduled")

    assert result2.raw_record_count == 0
    assert result2.skipped_count == 2
    assert "nothing new" in result2.log_message


@pytest.mark.asyncio
async def test_phishtank_dedup_ingests_only_new_entries(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first_batch = [
        {"phish_id": "4001", "url": "https://old.example.fr/a"},
    ]
    second_batch = [
        {"phish_id": "4001", "url": "https://old.example.fr/a"},  # dup
        {"phish_id": "4002", "url": "https://new.example.fr/b"},  # new
    ]

    store = RecordingSnapshotStore()

    async def fetch_first() -> list[dict[str, str]]:
        return first_batch

    service1 = PhishTankIngestionService(
        fetch_entries=fetch_first,
        snapshot_store=store,
    )
    async with session_factory() as session:
        result1 = await service1.run(session, trigger_mode="manual")
    assert result1.raw_record_count == 1

    async def fetch_second() -> list[dict[str, str]]:
        return second_batch

    service2 = PhishTankIngestionService(
        fetch_entries=fetch_second,
        snapshot_store=store,
    )
    async with session_factory() as session:
        result2 = await service2.run(session, trigger_mode="scheduled")

    assert result2.raw_record_count == 1
    assert result2.skipped_count == 1


# ---------------------------------------------------------------------------
# Tests — Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phishtank_empty_feed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def fetch_entries() -> list[dict[str, str]]:
        return []

    store = RecordingSnapshotStore()
    service = PhishTankIngestionService(
        fetch_entries=fetch_entries,
        snapshot_store=store,
    )

    async with session_factory() as session:
        result = await service.run(session, trigger_mode="scheduled")
        ingestion_run = await session.scalar(select(DataIngestionRun))

    assert result.raw_record_count == 0
    assert result.raw_object_count == 0
    assert "0 entries" in result.log_message
    assert ingestion_run is not None
    assert ingestion_run.status == "completed"


@pytest.mark.asyncio
async def test_phishtank_no_french_entries(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Feed has entries but none are French-targeted."""
    entries = [
        {"phish_id": "5001", "url": "https://paypal.com/login"},
        {"phish_id": "5002", "url": "https://wellsfargo.com/signin"},
    ]

    async def fetch_entries() -> list[dict[str, str]]:
        return entries

    store = RecordingSnapshotStore()
    service = PhishTankIngestionService(
        fetch_entries=fetch_entries,
        snapshot_store=store,
    )

    async with session_factory() as session:
        result = await service.run(session, trigger_mode="scheduled")

    assert result.raw_record_count == 0
    assert result.filtered_count == 2
    assert result.total_feed_count == 2
    assert "0 matched French" in result.log_message


@pytest.mark.asyncio
async def test_phishtank_entry_without_url_marked_unusable(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    entries = [
        {"phish_id": "6001", "url": "https://urssaf-update.example.fr"},
        {"phish_id": "6002"},  # no url — won't pass French filter
    ]

    async def fetch_entries() -> list[dict[str, str]]:
        return entries

    store = RecordingSnapshotStore()
    service = PhishTankIngestionService(
        fetch_entries=fetch_entries,
        snapshot_store=store,
    )

    async with session_factory() as session:
        result = await service.run(session, trigger_mode="scheduled")
        records = list((await session.scalars(select(DataRawRecord))).all())

    # Entry without URL has empty string → _is_french_target("") → False
    # So only the .fr entry passes the French filter
    assert result.raw_record_count == 1
    assert result.filtered_count == 1
    assert records[0].record_key == "6001"
    assert records[0].is_usable is True
