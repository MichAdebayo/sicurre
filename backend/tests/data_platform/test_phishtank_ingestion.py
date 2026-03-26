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

from sicurre_api.core.database import Base
from sicurre_api.domains.data_platform.models import (
    DataIngestionRun,
    DataRawObject,
    DataRawRecord,
)
from sicurre_api.domains.data_platform.services.phishtank import (
    PhishTankFeedClient,
    PhishTankIngestionService,
)
from sicurre_api.domains.data_platform.services.snapshot_storage import (
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
        engine, expire_on_commit=False, class_=AsyncSession,
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
    assert client.feed_url == (
        "https://data.phishtank.com/data/online-valid.json"
    )


def test_feed_url_with_api_key() -> None:
    client = PhishTankFeedClient(api_key="my-secret-key")
    assert client.feed_url == (
        "https://data.phishtank.com/data/my-secret-key/online-valid.json"
    )


def test_feed_url_custom_base_with_key() -> None:
    client = PhishTankFeedClient(
        feed_url="https://example.com/feed.json",
        api_key="abc123",
    )
    assert client.feed_url == "https://example.com/abc123/feed.json"


# ---------------------------------------------------------------------------
# Integration tests — full ingestion flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phishtank_ingestion_persists_lineage(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path,
) -> None:
    entries = [
        {
            "phish_id": "1001",
            "url": "https://secure-urssaf-fr.example/login",
            "verified": "yes",
        },
        {
            "phish_id": "1002",
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
            trigger_mode="scheduled",
            started_at=datetime(2026, 3, 25, 8, 0, tzinfo=timezone.utc),
        )

        ingestion_run = await session.scalar(select(DataIngestionRun))
        raw_object = await session.scalar(select(DataRawObject))
        raw_records = list(
            (await session.scalars(select(DataRawRecord))).all()
        )

    assert result.raw_object_count == 1
    assert result.raw_record_count == 2
    assert result.skipped_count == 0
    assert result.snapshot_path is not None
    assert result.snapshot_path.exists()
    assert result.snapshot_path.parent == tmp_path / "phishtank"
    assert result.snapshot_storage_uri.endswith(".json")
    assert ingestion_run is not None
    assert ingestion_run.status == "completed"
    assert ingestion_run.trigger_mode == "scheduled"
    assert ingestion_run.raw_object_count == 1
    assert ingestion_run.raw_record_count == 2
    assert raw_object is not None
    assert raw_object.object_type == "api_payload"
    assert raw_object.storage_uri is not None
    assert raw_object.storage_uri == result.snapshot_storage_uri
    assert raw_object.storage_uri.endswith(".json")
    assert len(raw_records) == 2
    assert {record.record_key for record in raw_records} == {"1001", "1002"}


@pytest.mark.asyncio
async def test_phishtank_ingestion_uses_source_prefix_for_r2_keys(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    entries = [
        {"phish_id": "1001", "url": "https://secure-urssaf-fr.example/login"},
    ]
    recording_store = RecordingSnapshotStore()

    async def fetch_entries() -> list[dict[str, str]]:
        return entries

    service = PhishTankIngestionService(
        fetch_entries=fetch_entries,
        snapshot_store=recording_store,
    )

    async with session_factory() as session:
        result = await service.run(session, trigger_mode="scheduled")

    assert recording_store.object_key is not None
    assert recording_store.object_key.startswith("raw-snapshots/phishtank/")
    assert result.snapshot_path is None
    assert result.snapshot_storage_uri.startswith(
        "r2://sicurre-raw/raw-snapshots/phishtank/"
    )


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
    assert ingestion_run.raw_object_count == 0
    assert ingestion_run.raw_record_count == 0


# ---------------------------------------------------------------------------
# Tests — Deduplication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phishtank_dedup_skips_already_ingested(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Second run with same entries → all skipped, zero new records."""
    entries = [
        {"phish_id": "2001", "url": "https://fake-banque.example/connecter"},
        {"phish_id": "2002", "url": "https://faux-impots.example/verifier"},
    ]

    async def fetch_entries() -> list[dict[str, str]]:
        return entries

    store = RecordingSnapshotStore()
    service = PhishTankIngestionService(
        fetch_entries=fetch_entries,
        snapshot_store=store,
    )

    # First run — should ingest both
    async with session_factory() as session:
        result1 = await service.run(session, trigger_mode="scheduled")

    assert result1.raw_record_count == 2
    assert result1.skipped_count == 0

    # Second run — should skip both
    async with session_factory() as session:
        result2 = await service.run(session, trigger_mode="scheduled")

    assert result2.raw_record_count == 0
    assert result2.skipped_count == 2
    assert "nothing new" in result2.log_message


@pytest.mark.asyncio
async def test_phishtank_dedup_ingests_only_new_entries(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Second run with mix of old + new entries → only new ones ingested."""
    first_batch = [
        {"phish_id": "3001", "url": "https://old.example/a"},
    ]
    second_batch = [
        {"phish_id": "3001", "url": "https://old.example/a"},  # dup
        {"phish_id": "3002", "url": "https://new.example/b"},  # new
    ]

    store = RecordingSnapshotStore()

    async def fetch_first() -> list[dict[str, str]]:
        return first_batch

    service1 = PhishTankIngestionService(
        fetch_entries=fetch_first,
        snapshot_store=store,
    )
    async with session_factory() as session:
        result1 = await service1.run(session, trigger_mode="scheduled")

    assert result1.raw_record_count == 1

    async def fetch_second() -> list[dict[str, str]]:
        return second_batch

    service2 = PhishTankIngestionService(
        fetch_entries=fetch_second,
        snapshot_store=store,
    )
    async with session_factory() as session:
        result2 = await service2.run(session, trigger_mode="scheduled")

    assert result2.raw_record_count == 1  # only phish_id 3002
    assert result2.skipped_count == 1  # phish_id 3001 skipped


# ---------------------------------------------------------------------------
# Tests — Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phishtank_empty_feed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Empty feed → completed with zero counts, not an error."""

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
    assert result.skipped_count == 0
    assert "0 entries" in result.log_message
    assert ingestion_run is not None
    assert ingestion_run.status == "completed"


@pytest.mark.asyncio
async def test_phishtank_entry_without_url_marked_unusable(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Entry missing ``url`` → stored but marked ``is_usable=False``."""
    entries = [
        {"phish_id": "4001"},  # no url
        {"phish_id": "4002", "url": "https://legit.example/phish"},
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
        records = list(
            (await session.scalars(select(DataRawRecord))).all()
        )

    assert result.raw_record_count == 2
    usable = [r for r in records if r.is_usable]
    unusable = [r for r in records if not r.is_usable]
    assert len(usable) == 1
    assert len(unusable) == 1
    assert unusable[0].rejection_reason == "missing_url"
    assert unusable[0].record_key == "4001"
