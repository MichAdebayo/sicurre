from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from sicurre_api.core.database import Base
from sicurre_api.domains.data_platform.models import (
    DataIngestionRun,
    DataRawObject,
    DataRawRecord,
)
from sicurre_api.domains.data_platform.services.phishtank import (
    PhishTankIngestionService,
)


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        yield factory
    finally:
        await engine.dispose()


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

    service = PhishTankIngestionService(
        fetch_entries=fetch_entries,
        snapshot_dir=tmp_path,
    )

    async with session_factory() as session:
        result = await service.run(
            session,
            trigger_mode="scheduled",
            started_at=datetime(2026, 3, 25, 8, 0, tzinfo=timezone.utc),
        )

        ingestion_run = await session.scalar(select(DataIngestionRun))
        raw_object = await session.scalar(select(DataRawObject))
        raw_records = list((await session.scalars(select(DataRawRecord))).all())

    assert result.raw_object_count == 1
    assert result.raw_record_count == 2
    assert result.snapshot_path.exists()
    assert ingestion_run is not None
    assert ingestion_run.status == "completed"
    assert ingestion_run.trigger_mode == "scheduled"
    assert ingestion_run.raw_object_count == 1
    assert ingestion_run.raw_record_count == 2
    assert raw_object is not None
    assert raw_object.object_type == "api_payload"
    assert raw_object.storage_uri.endswith(".json")
    assert len(raw_records) == 2
    assert {record.record_key for record in raw_records} == {"1001", "1002"}


@pytest.mark.asyncio
async def test_phishtank_ingestion_marks_failed_runs(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path,
) -> None:
    async def fetch_entries() -> list[dict[str, str]]:
        raise RuntimeError("feed unavailable")

    service = PhishTankIngestionService(
        fetch_entries=fetch_entries,
        snapshot_dir=tmp_path,
    )

    async with session_factory() as session:
        with pytest.raises(RuntimeError, match="feed unavailable"):
            await service.run(session, trigger_mode="scheduled")

        ingestion_run = await session.scalar(select(DataIngestionRun))

    assert ingestion_run is not None
    assert ingestion_run.status == "failed"
    assert ingestion_run.raw_object_count == 0
    assert ingestion_run.raw_record_count == 0
