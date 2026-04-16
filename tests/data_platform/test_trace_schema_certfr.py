"""Trace schema tests for CertFRIngestionService.

Verifies that SemanticTraceLogger emits correctly structured JSON traces
to stdout across the happy path and failure path.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base
from data_platform.extractors.certfr import CertFRIngestionService
from data_platform.services.snapshot_storage import SnapshotWriteResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_traces(capsys_output: str) -> list[dict[str, Any]]:
    """Parse each non-empty stdout line as a JSON trace dict."""
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
    """Assert required fields are present and well-typed on every trace."""
    assert trace["parent_type"] == "Web Scraping"
    assert trace["child_target"] == "CERT-FR"
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


_SAMPLE_ENTRIES: dict[str, list[dict[str, Any]]] = {
    "actualite": [
        {
            "title": "Bulletin CERTFR-2025-ACT-001",
            "link": "https://www.cert.ssi.gouv.fr/actualite/CERTFR-2025-ACT-001/",
            "guid": "https://www.cert.ssi.gouv.fr/actualite/CERTFR-2025-ACT-001/",
            "published": "Mon, 01 Jan 2025 00:00:00 +0000",
            "summary": "Résumé actualité.",
        }
    ],
    "alerte": [
        {
            "title": "Alerte CERTFR-2025-ALE-001",
            "link": "https://www.cert.ssi.gouv.fr/alerte/CERTFR-2025-ALE-001/",
            "guid": "https://www.cert.ssi.gouv.fr/alerte/CERTFR-2025-ALE-001/",
            "published": "Tue, 02 Jan 2025 00:00:00 +0000",
            "summary": "Résumé alerte.",
        }
    ],
    "cti": [
        {
            "title": "CTI CERTFR-2025-CTI-001",
            "link": "https://www.cert.ssi.gouv.fr/cti/CERTFR-2025-CTI-001/",
            "guid": "https://www.cert.ssi.gouv.fr/cti/CERTFR-2025-CTI-001/",
            "published": "Wed, 03 Jan 2025 00:00:00 +0000",
            "summary": "Résumé CTI.",
        }
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_certfr_trace_happy_path_schema(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """Happy path emits correctly ordered traces with valid schema on every line."""

    async def fetch_entries() -> dict[str, list[dict[str, Any]]]:
        return _SAMPLE_ENTRIES

    service = CertFRIngestionService(
        fetch_entries=fetch_entries,
        snapshot_store=_RecordingStore(),
    )

    async with session_factory() as session:
        result = await service.run(
            session,
            trigger_mode="scheduled",
            started_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

    traces = parse_traces(capsys.readouterr().out)

    # Every trace must conform to the schema
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


@pytest.mark.asyncio
async def test_certfr_trace_id_updated_after_run_created(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """trace_id must be 'run-pending' on orchestration/start, then a real UUID after."""

    async def fetch_entries() -> dict[str, list[dict[str, Any]]]:
        return _SAMPLE_ENTRIES

    service = CertFRIngestionService(
        fetch_entries=fetch_entries,
        snapshot_store=_RecordingStore(),
    )

    async with session_factory() as session:
        await service.run(session)

    traces = parse_traces(capsys.readouterr().out)
    assert traces[0]["trace_id"] == "run-pending"
    real_id = traces[1]["trace_id"]
    assert real_id != "run-pending"
    # All subsequent traces share the same real ID
    for t in traces[1:]:
        assert t["trace_id"] == real_id


@pytest.mark.asyncio
async def test_certfr_trace_ingestion_success_metrics(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """ingestion/success trace carries correct metrics."""

    async def fetch_entries() -> dict[str, list[dict[str, Any]]]:
        return _SAMPLE_ENTRIES

    service = CertFRIngestionService(
        fetch_entries=fetch_entries,
        snapshot_store=_RecordingStore(),
    )

    async with session_factory() as session:
        await service.run(session)

    traces = parse_traces(capsys.readouterr().out)
    ingestion_success = next(
        t for t in traces if t["stage"] == "ingestion" and t["status"] == "success"
    )
    assert ingestion_success["metrics"]["new_records"] == 3
    assert ingestion_success["metrics"]["feed_count"] == 3


@pytest.mark.asyncio
async def test_certfr_trace_failure_path(
    session_factory: async_sessionmaker[AsyncSession],
    capsys,
) -> None:
    """On fetch error, orchestration/failed is emitted and the exception re-raises."""

    async def fetch_entries() -> dict[str, list[dict[str, Any]]]:
        raise RuntimeError("RSS feed unreachable")

    service = CertFRIngestionService(
        fetch_entries=fetch_entries,
        snapshot_store=_RecordingStore(),
    )

    async with session_factory() as session:
        with pytest.raises(RuntimeError, match="RSS feed unreachable"):
            await service.run(session)

    traces = parse_traces(capsys.readouterr().out)
    statuses = [(t["stage"], t["status"]) for t in traces]
    assert ("orchestration", "failed") in statuses
    failed = next(t for t in traces if t["status"] == "failed")
    assert "RSS feed unreachable" in failed["message"]
