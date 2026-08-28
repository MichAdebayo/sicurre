"""Tests for SEKOIA Community IOC ingestion."""

from __future__ import annotations

import json
import zipfile
from collections.abc import AsyncIterator
from io import BytesIO

import pytest
import pytest_asyncio
import respx
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base
from data_platform.extractors.sekoia_ioc import (
    DEFAULT_ARCHIVE_URL,
    DEFAULT_RAW_ROOT,
    SekoiaCommunityClient,
    SekoiaFetchedPayload,
    SekoiaIoc,
    SekoiaIocIngestionService,
    classify_ioc,
    parse_ioc_file,
)
from data_platform.services.shared.snapshot_storage import SnapshotWriteResult
from db.models import DataRawObject, DataRawRecord, DataSourceSystem


class RecordingSnapshotStore:
    def __init__(self) -> None:
        self.object_key: str | None = None
        self.payload: bytes | None = None

    def build_object_key(self, *, source_prefix: str, filename: str) -> str:
        return f"raw-snapshots/{source_prefix}/{filename}"

    async def write_snapshot(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str,
    ) -> SnapshotWriteResult:
        del content_type
        self.object_key = object_key
        self.payload = payload
        return SnapshotWriteResult(
            storage_uri=f"r2://sicurre-raw/{object_key}",
            content_hash="sekoia-hash",
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

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield factory
    finally:
        await engine.dispose()


def test_classify_ioc_recognizes_supported_indicator_types() -> None:
    assert classify_ioc("https://evil.example/login")[0] == "url"
    assert classify_ioc("florenceorganics.us") == ("domain", "florenceorganics.us")
    assert classify_ioc("198.51.100.42") == ("ipv4", "198.51.100.42")
    assert classify_ioc("A" * 64) == ("hash", "a" * 64)
    assert classify_ioc("not an indicator")[0] == "unknown"


def test_parse_sekoia_csv_with_sneaky2fa_headers() -> None:
    content = (
        "ioc,first seen,domain creation,description,comment\n"
        "FlorenceOrganics.us,2024-10-08,2022-04-19,"
        "attacker-controlled domain,Sneaky2FA\n"
    )

    rows = parse_ioc_file(
        content,
        source_path="IOCs/sneaky2fa/sneaky2fa_iocs_20250116.csv",
        source_url="https://example.test/sneaky.csv",
    )

    assert len(rows) == 1
    assert rows[0].campaign == "sneaky2fa"
    assert rows[0].ioc_type == "domain"
    assert rows[0].value == "florenceorganics.us"
    assert rows[0].first_seen == "2024-10-08"
    assert rows[0].description == "attacker-controlled domain"


def test_parse_sekoia_csv_with_tycoon2fa_headers() -> None:
    content = (
        "IOC,Valid From,Valid Until,Link\n"
        "https://login.example.test/session,2024-03-25,2024-04-25,"
        "https://blog.sekoia.io/example\n"
    )

    rows = parse_ioc_file(
        content,
        source_path="IOCs/tycoon2fa/tycoon2fa_iocs_20240325.csv",
    )

    assert len(rows) == 1
    assert rows[0].campaign == "tycoon2fa"
    assert rows[0].ioc_type == "url"
    assert rows[0].first_seen == "2024-03-25"
    assert rows[0].valid_until == "2024-04-25"


@pytest.mark.asyncio
@respx.mock
async def test_sekoia_client_discovers_files_with_one_tree_request() -> None:
    api_root = "https://api.github.test/repos/community/git/trees/main"
    tree_route = respx.get(f"{api_root}?recursive=1").mock(
        return_value=Response(
            200,
            json={
                "truncated": False,
                "tree": [
                    "malformed-entry",
                    {
                        "type": "blob",
                        "path": "IOCs/sneaky2fa/iocs.csv",
                    },
                    {"type": "blob", "path": "IOCs/unselected/iocs.csv"},
                ],
            },
        )
    )
    respx.get(f"{DEFAULT_RAW_ROOT}/IOCs/sneaky2fa/iocs.csv").mock(
        return_value=Response(200, text="ioc\nmalicious.example\n")
    )

    payload = await SekoiaCommunityClient(
        api_root=api_root,
        target_paths=("sneaky2fa",),
    ).fetch_iocs()

    assert tree_route.call_count == 1
    assert [ioc.value for ioc in payload.iocs] == ["malicious.example"]


@pytest.mark.asyncio
@respx.mock
async def test_sekoia_client_falls_back_to_public_archive_on_rate_limit() -> None:
    archive_buffer = BytesIO()
    with zipfile.ZipFile(archive_buffer, mode="w") as archive:
        archive.writestr(
            "Community-main/IOCs/sneaky2fa/iocs.csv",
            "ioc\narchive-malicious.example\n",
        )
        archive.writestr(
            "Community-main/IOCs/unselected/iocs.csv",
            "ioc\nignored.example\n",
        )

    api_root = "https://api.github.test/repos/community/git/trees/main"
    respx.get(f"{api_root}?recursive=1").mock(return_value=Response(403))
    archive_route = respx.get(DEFAULT_ARCHIVE_URL).mock(
        return_value=Response(200, content=archive_buffer.getvalue())
    )

    payload = await SekoiaCommunityClient(
        api_root=api_root,
        target_paths=("sneaky2fa",),
    ).fetch_iocs()

    assert archive_route.call_count == 1
    assert [ioc.value for ioc in payload.iocs] == ["archive-malicious.example"]


@pytest.mark.asyncio
async def test_sekoia_ingestion_persists_failure_status(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def failed_fetch() -> SekoiaFetchedPayload:
        raise RuntimeError("source unavailable")

    service = SekoiaIocIngestionService(
        fetch_iocs=failed_fetch,
        snapshot_store=RecordingSnapshotStore(),
    )

    async with session_factory() as session:
        with pytest.raises(RuntimeError, match="source unavailable"):
            await service.run(session, trigger_mode="manual")

        from db.models import DataIngestionRun

        run = await session.scalar(select(DataIngestionRun))

    assert run is not None
    assert run.status == "failed"
    assert run.finished_at is not None


@pytest.mark.asyncio
async def test_sekoia_ingestion_persists_source_lineage(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ioc = SekoiaIoc(
        value="florenceorganics.us",
        ioc_type="domain",
        campaign="sneaky2fa",
        source_path="IOCs/sneaky2fa/sneaky2fa_iocs_20250116.csv",
        first_seen="2024-10-08",
        description="attacker-controlled domain",
    )
    payload = SekoiaFetchedPayload(
        iocs=[ioc],
        snapshot_bytes=json.dumps({"records": [{"ioc": ioc.value}]}).encode("utf-8"),
    )

    async def fetch_iocs() -> SekoiaFetchedPayload:
        return payload

    store = RecordingSnapshotStore()
    service = SekoiaIocIngestionService(
        fetch_iocs=fetch_iocs,
        snapshot_store=store,
        snapshot_prefix="cron/scraping/sekoia_ioc",
    )

    async with session_factory() as session:
        result = await service.run(session, trigger_mode="manual")
        source = await session.scalar(select(DataSourceSystem))
        raw_object = await session.scalar(select(DataRawObject))
        raw_record = await session.scalar(select(DataRawRecord))

    assert result.raw_object_count == 1
    assert result.raw_record_count == 1
    assert result.skipped_count == 0
    assert source is not None
    assert source.name == "sekoia-community-ioc"
    assert source.source_type == "scraping"
    assert raw_object is not None
    assert raw_object.source_metadata["source"] == "sekoia_ioc"
    assert raw_record is not None
    assert raw_record.source_system_id == source.id
    assert raw_record.is_usable is False
    assert raw_record.rejection_reason == "ioc_reference_only_not_email_training_text"
    assert json.loads(raw_record.raw_content)["label"] == "phishing"
    assert store.object_key is not None
    assert "cron/scraping/sekoia_ioc" in store.object_key


@pytest.mark.asyncio
async def test_sekoia_ingestion_skips_duplicate_iocs(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ioc = SekoiaIoc(
        value="florenceorganics.us",
        ioc_type="domain",
        campaign="sneaky2fa",
        source_path="IOCs/sneaky2fa/sneaky2fa_iocs_20250116.csv",
    )
    payload = SekoiaFetchedPayload(
        iocs=[ioc],
        snapshot_bytes=json.dumps({"records": [{"ioc": ioc.value}]}).encode("utf-8"),
    )

    async def fetch_iocs() -> SekoiaFetchedPayload:
        return payload

    service = SekoiaIocIngestionService(
        fetch_iocs=fetch_iocs,
        snapshot_store=RecordingSnapshotStore(),
    )

    async with session_factory() as session:
        first = await service.run(session, trigger_mode="manual")
        second = await service.run(session, trigger_mode="manual")
        records = list((await session.scalars(select(DataRawRecord))).all())

    assert first.raw_record_count == 1
    assert second.raw_record_count == 0
    assert second.skipped_count == 1
    assert len(records) == 1
