"""Trace schema tests for CommonCrawlIngestionService.

Verifies that SemanticTraceLogger emits correctly structured JSON traces
to stdout across the happy path, empty-pipeline path, zero-delta path,
and failure path.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base
from data_platform.extractors.common_crawl_ingestion import (
    CommonCrawlBigQueryClient,
    CommonCrawlIngestionService,
)
from data_platform.services.shared.snapshot_storage import SnapshotWriteResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_traces(capsys_output: str) -> list[dict[str, Any]]:
    traces = []
    for line in capsys_output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if "stage" in obj and "status" in obj:
                traces.append(obj)
        except json.JSONDecodeError:
            pass
    return traces


def assert_trace_schema(trace: dict[str, Any]) -> None:
    assert trace["parent_type"] == "Big Data"
    assert trace["child_target"] == "Common Crawl"
    assert trace["domain"] == "data_platform"
    assert trace["stage"] in {
        "orchestration",
        "ingestion",
        "snapshot",
        "extraction",
        "normalization",
        "pii_scrubbing",
        "annotation",
        "dataset_freeze",
        "classification",
        "remediation",
    }
    assert trace["status"] in {"start", "success", "failed", "skipped"}
    assert isinstance(trace["message"], str)
    assert isinstance(trace["trace_id"], str)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _RecordingStore:
    def build_object_key(self, *, source_prefix: str, filename: str) -> str:
        return f"raw-snapshots/{source_prefix}/{filename}"

    async def write_snapshot(
        self, *, object_key: str, payload: bytes, content_type: str
    ) -> SnapshotWriteResult:
        return SnapshotWriteResult(
            storage_uri=f"local://{object_key}",
            content_hash="testhash",
            size_bytes=len(payload),
            local_path=None,
        )


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield factory
    finally:
        await engine.dispose()


_SAMPLE_ENTRIES = [
    {
        "record_key": "fp-111",
        "url": "https://evil.fr/phish",
        "text": "Votre compte est bloqué, cliquez ici.",
        "label": "phishing",
        "category": "phishing_related",
        "language": "fr",
        "crawl_id": "CC-2025-01",
        "query": "phishing français",
        "query_label": "phishing",
        "content_hash": "abc123",
    },
    {
        "record_key": "fp-222",
        "url": "https://spam.fr/offer",
        "text": "Offre exclusive! Répondez vite.",
        "label": "spam",
        "category": "spam_like",
        "language": "fr",
        "crawl_id": "CC-2025-01",
        "query": "spam français",
        "query_label": "spam",
        "content_hash": "def456",
    },
]

_LOCAL_BACKEND_KEYS_SAME_CONTENT = [
    {
        **_SAMPLE_ENTRIES[0],
        "record_key": "local-sha-111",
    },
    {
        **_SAMPLE_ENTRIES[1],
        "record_key": "local-sha-222",
    },
]


def _make_bq_client(entries: list[dict[str, Any]]) -> CommonCrawlBigQueryClient:
    client = CommonCrawlBigQueryClient.__new__(CommonCrawlBigQueryClient)
    client.full_table_id = "sicurre-test.sicurre_dataset.common_crawl_raw"
    client.fetch_latest_parquet_from_r2 = MagicMock(return_value=pd.DataFrame())
    client.execute_bigquery_pipeline = MagicMock(return_value=entries)
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_common_crawl_trace_happy_path_schema(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """Happy path emits correctly ordered traces with valid schema."""
    service = CommonCrawlIngestionService(
        bq_client=_make_bq_client(_SAMPLE_ENTRIES),
        snapshot_store=_RecordingStore(),
    )

    async with session_factory() as session:
        result = await service.run(
            session,
            trigger_mode="manual",
            started_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

    traces = parse_traces(capsys.readouterr().out)

    for t in traces:
        assert_trace_schema(t)

    stages = [(t["stage"], t["status"]) for t in traces]
    assert stages == [
        ("orchestration", "start"),
        ("extraction", "start"),
        ("extraction", "success"),
        ("snapshot", "success"),
        ("ingestion", "success"),
        ("orchestration", "success"),
    ]
    assert result.raw_record_count == 2


@pytest.mark.asyncio
async def test_common_crawl_trace_id_updated_after_run_created(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """trace_id must be 'run-pending' on orchestration/start, then a real UUID."""
    service = CommonCrawlIngestionService(
        bq_client=_make_bq_client(_SAMPLE_ENTRIES),
        snapshot_store=_RecordingStore(),
    )

    async with session_factory() as session:
        await service.run(session)

    traces = parse_traces(capsys.readouterr().out)
    assert traces[0]["trace_id"] == "run-pending"
    real_id = traces[1]["trace_id"]
    assert real_id != "run-pending"
    for t in traces[1:]:
        assert t["trace_id"] == real_id


@pytest.mark.asyncio
async def test_common_crawl_trace_extraction_success_metrics(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """extraction/success trace carries total_extracted metric."""
    service = CommonCrawlIngestionService(
        bq_client=_make_bq_client(_SAMPLE_ENTRIES),
        snapshot_store=_RecordingStore(),
    )

    async with session_factory() as session:
        await service.run(session)

    traces = parse_traces(capsys.readouterr().out)
    extraction_ok = next(
        t for t in traces if t["stage"] == "extraction" and t["status"] == "success"
    )
    assert extraction_ok["metrics"]["total_extracted"] == 2


@pytest.mark.asyncio
async def test_common_crawl_trace_empty_pipeline(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """When BigQuery returns 0 entries, extraction/success(0) then orchestration/success."""
    service = CommonCrawlIngestionService(
        bq_client=_make_bq_client([]),
        snapshot_store=_RecordingStore(),
    )

    async with session_factory() as session:
        result = await service.run(session)

    traces = parse_traces(capsys.readouterr().out)
    for t in traces:
        assert_trace_schema(t)

    stages = [(t["stage"], t["status"]) for t in traces]
    assert stages == [
        ("orchestration", "start"),
        ("extraction", "start"),
        ("extraction", "success"),
        ("orchestration", "success"),
    ]
    extraction_ok = next(
        t for t in traces if t["stage"] == "extraction" and t["status"] == "success"
    )
    assert extraction_ok["metrics"]["total_extracted"] == 0
    assert result.raw_record_count == 0


@pytest.mark.asyncio
async def test_common_crawl_trace_zero_delta_skipped(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """Second run with identical record_keys emits ingestion/skipped."""
    service = CommonCrawlIngestionService(
        bq_client=_make_bq_client(_SAMPLE_ENTRIES),
        snapshot_store=_RecordingStore(),
    )

    async with session_factory() as session:
        await service.run(session)
        capsys.readouterr()

        await service.run(session)

    traces = parse_traces(capsys.readouterr().out)
    stages = [(t["stage"], t["status"]) for t in traces]
    assert ("ingestion", "skipped") in stages
    assert ("orchestration", "success") in stages


@pytest.mark.asyncio
async def test_common_crawl_trace_zero_delta_skipped_when_backend_keys_change(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """Dedup stays stable when the backend changes record_key but content_hash matches."""
    first_service = CommonCrawlIngestionService(
        bq_client=_make_bq_client(_SAMPLE_ENTRIES),
        snapshot_store=_RecordingStore(),
    )
    second_service = CommonCrawlIngestionService(
        bq_client=_make_bq_client(_LOCAL_BACKEND_KEYS_SAME_CONTENT),
        snapshot_store=_RecordingStore(),
    )

    async with session_factory() as session:
        await first_service.run(session)
        capsys.readouterr()

        result = await second_service.run(session)

    traces = parse_traces(capsys.readouterr().out)
    stages = [(t["stage"], t["status"]) for t in traces]
    assert result.raw_record_count == 0
    assert result.skipped_count == 2
    assert ("ingestion", "skipped") in stages


@pytest.mark.asyncio
async def test_common_crawl_trace_failure_path(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """On pipeline error, orchestration/failed is emitted and exception re-raises."""
    client = CommonCrawlBigQueryClient.__new__(CommonCrawlBigQueryClient)
    client.full_table_id = "sicurre-test.sicurre_dataset.common_crawl_raw"
    client.fetch_latest_parquet_from_r2 = MagicMock(
        side_effect=FileNotFoundError("R2 bucket introuvable")
    )
    client.execute_bigquery_pipeline = MagicMock(return_value=[])

    service = CommonCrawlIngestionService(
        bq_client=client,
        snapshot_store=_RecordingStore(),
    )

    async with session_factory() as session:
        with pytest.raises(FileNotFoundError, match="R2 bucket introuvable"):
            await service.run(session)

    traces = parse_traces(capsys.readouterr().out)
    failed = next(t for t in traces if t["status"] == "failed")
    assert failed["stage"] == "orchestration"
    assert "R2 bucket introuvable" in failed["message"]
