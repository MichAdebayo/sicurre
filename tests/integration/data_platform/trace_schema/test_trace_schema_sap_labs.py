"""Trace schema tests for SapLabsIngestionService.

Verifies that SemanticTraceLogger emits correctly structured JSON traces
to stdout across the happy path, zero-delta path, empty-scraper path,
and failure path.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base
from data_platform.extractors.sap_labs import (
    SapLabsIngestionService,
    SapLabsScraperClient,
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
    assert trace["parent_type"] == "Web Scraping"
    assert trace["child_target"] == "SAP Labs Blog"
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
        "id": "sap-001",
        "subject": "Votre colis est bloqué",
        "body": "Cliquez ici.",
        "label": "phishing",
    },
    {
        "id": "sap-002",
        "subject": "Remboursement CPAM",
        "body": "Connectez-vous.",
        "label": "phishing",
    },
]


def _make_service(entries: list[dict[str, Any]]) -> SapLabsIngestionService:
    scraper = SapLabsScraperClient.__new__(SapLabsScraperClient)
    scraper.url = "https://example.com/fake"
    scraper.fetch_entries = AsyncMock(return_value=entries)
    return SapLabsIngestionService(
        scraper_client=scraper,
        snapshot_store=_RecordingStore(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sap_labs_trace_happy_path_schema(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """Happy path emits correctly ordered traces with valid schema."""
    service = _make_service(_SAMPLE_ENTRIES)

    async with session_factory() as session:
        result = await service.run(
            session,
            trigger_mode="manual",
            started_at=datetime(2025, 1, 1, tzinfo=UTC),
        )

    traces = parse_traces(capsys.readouterr().out)

    for t in traces:
        assert_trace_schema(t)

    stages = [(t["stage"], t["status"]) for t in traces]
    assert stages == [
        ("orchestration", "start"),
        ("ingestion", "start"),
        ("snapshot", "success"),
        ("ingestion", "success"),
        ("orchestration", "success"),
    ]
    assert result.raw_record_count == 2


@pytest.mark.asyncio
async def test_sap_labs_trace_id_updated_after_run_created(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """trace_id must be 'run-pending' on orchestration/start, then a real UUID."""
    service = _make_service(_SAMPLE_ENTRIES)

    async with session_factory() as session:
        await service.run(session)

    traces = parse_traces(capsys.readouterr().out)
    assert traces[0]["trace_id"] == "run-pending"
    real_id = traces[1]["trace_id"]
    assert real_id != "run-pending"
    for t in traces[1:]:
        assert t["trace_id"] == real_id


@pytest.mark.asyncio
async def test_sap_labs_trace_ingestion_success_metrics(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """ingestion/success trace carries new_records and skipped metrics."""
    service = _make_service(_SAMPLE_ENTRIES)

    async with session_factory() as session:
        await service.run(session)

    traces = parse_traces(capsys.readouterr().out)
    success = next(
        t for t in traces if t["stage"] == "ingestion" and t["status"] == "success"
    )
    assert success["metrics"]["new_records"] == 2
    assert success["metrics"]["skipped"] == 0


@pytest.mark.asyncio
async def test_sap_labs_trace_zero_delta_skipped(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """Second run with identical entries emits ingestion/skipped."""
    service = _make_service(_SAMPLE_ENTRIES)

    async with session_factory() as session:
        # First run ingests both entries
        await service.run(session)
        capsys.readouterr()  # clear first-run output

        # Second run — same service instance reuses same source_name → dedup fires
        await service.run(session)

    traces = parse_traces(capsys.readouterr().out)
    stages = [(t["stage"], t["status"]) for t in traces]
    assert ("ingestion", "skipped") in stages
    assert ("orchestration", "success") in stages
    skipped = next(
        t for t in traces if t["stage"] == "ingestion" and t["status"] == "skipped"
    )
    assert skipped["metrics"]["skipped"] == 2


@pytest.mark.asyncio
async def test_sap_labs_trace_empty_scraper_skipped(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """When scraper returns 0 entries, ingestion/skipped + orchestration/success are emitted."""
    service = _make_service([])

    async with session_factory() as session:
        result = await service.run(session)

    traces = parse_traces(capsys.readouterr().out)
    for t in traces:
        assert_trace_schema(t)

    stages = [(t["stage"], t["status"]) for t in traces]
    assert ("ingestion", "skipped") in stages
    assert ("orchestration", "success") in stages
    assert result.raw_record_count == 0


@pytest.mark.asyncio
async def test_sap_labs_trace_failure_path(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """On scraper error, orchestration/failed is emitted and exception re-raises."""
    scraper = SapLabsScraperClient.__new__(SapLabsScraperClient)
    scraper.url = "https://example.com/fake"
    scraper.fetch_entries = AsyncMock(side_effect=RuntimeError("réseau indisponible"))
    service = SapLabsIngestionService(
        scraper_client=scraper,
        snapshot_store=_RecordingStore(),
    )

    async with session_factory() as session:
        with pytest.raises(RuntimeError, match="réseau indisponible"):
            await service.run(session)

    traces = parse_traces(capsys.readouterr().out)
    failed = next(t for t in traces if t["status"] == "failed")
    assert failed["stage"] == "orchestration"
    assert "réseau indisponible" in failed["message"]
