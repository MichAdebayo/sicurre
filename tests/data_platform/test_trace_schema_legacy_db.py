"""Trace schema tests for LegacyDbIngestionService.

Verifies that SemanticTraceLogger emits correctly structured JSON traces
to stdout across the happy path, empty-DB path, and failure path.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base
from data_platform.extractors.legacy_db import (
    LegacyDbConnector,
    LegacyDbIngestionService,
)
from data_platform.services.snapshot_storage import SnapshotWriteResult


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
    assert trace["parent_type"] == "Database"
    assert trace["child_target"] == "Historical DB"
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
        "threat_id": "t-001",
        "message_id": "msg-001",
        "subject": "Votre compte bancaire est suspendu",
        "body_preview": "Cliquez immédiatement pour débloquer.",
        "verdict": "phishing",
        "confidence": 0.97,
        "signals": None,
        "archetype": "banking",
        "source_dataset": "legacy",
        "received_at": None,
        "user_email": "user@example.fr",
    },
    {
        "threat_id": "t-002",
        "message_id": "msg-002",
        "subject": "Offre spéciale Amazon",
        "body_preview": "Profitez de -50% sur tout le site.",
        "verdict": "spam",
        "confidence": 0.75,
        "signals": None,
        "archetype": None,
        "source_dataset": "legacy",
        "received_at": None,
        "user_email": "user2@example.fr",
    },
]


def _make_service(entries: list[dict[str, Any]]) -> LegacyDbIngestionService:
    connector = LegacyDbConnector.__new__(LegacyDbConnector)
    connector.db_url = "sqlite+aiosqlite:///:memory:"
    connector.fetch_threats = AsyncMock(return_value=entries)
    return LegacyDbIngestionService(
        connector=connector,
        snapshot_store=_RecordingStore(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_db_trace_happy_path_schema(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """Happy path emits correctly ordered traces with valid schema."""
    service = _make_service(_SAMPLE_ENTRIES)

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
        ("ingestion", "start"),
        ("snapshot", "success"),
        ("ingestion", "success"),
        ("orchestration", "success"),
    ]
    assert result.raw_record_count == 2


@pytest.mark.asyncio
async def test_legacy_db_trace_id_updated_after_run_created(
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
async def test_legacy_db_trace_extraction_success_metrics(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """extraction/success trace carries total_extracted metric."""
    service = _make_service(_SAMPLE_ENTRIES)

    async with session_factory() as session:
        await service.run(session)

    traces = parse_traces(capsys.readouterr().out)
    extraction_ok = next(
        t for t in traces if t["stage"] == "extraction" and t["status"] == "success"
    )
    assert extraction_ok["metrics"]["total_extracted"] == 2


@pytest.mark.asyncio
async def test_legacy_db_trace_ingestion_success_metrics(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """ingestion/success trace carries new_records and total_extracted metrics."""
    service = _make_service(_SAMPLE_ENTRIES)

    async with session_factory() as session:
        await service.run(session)

    traces = parse_traces(capsys.readouterr().out)
    ingestion_ok = next(
        t for t in traces if t["stage"] == "ingestion" and t["status"] == "success"
    )
    assert ingestion_ok["metrics"]["new_records"] == 2
    assert ingestion_ok["metrics"]["total_extracted"] == 2


@pytest.mark.asyncio
async def test_legacy_db_trace_empty_db(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """When legacy DB has 0 rows, extraction/success(0) then orchestration/success."""
    service = _make_service([])

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
async def test_legacy_db_trace_failure_path(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """On connector error, orchestration/failed is emitted and exception re-raises."""
    connector = LegacyDbConnector.__new__(LegacyDbConnector)
    connector.db_url = "sqlite+aiosqlite:///:memory:"
    connector.fetch_threats = AsyncMock(
        side_effect=FileNotFoundError("Base de données externe introuvable")
    )
    service = LegacyDbIngestionService(
        connector=connector,
        snapshot_store=_RecordingStore(),
    )

    async with session_factory() as session:
        with pytest.raises(
            FileNotFoundError, match="Base de données externe introuvable"
        ):
            await service.run(session)

    traces = parse_traces(capsys.readouterr().out)
    failed = next(t for t in traces if t["status"] == "failed")
    assert failed["stage"] == "orchestration"
    assert "Base de données externe introuvable" in failed["message"]
