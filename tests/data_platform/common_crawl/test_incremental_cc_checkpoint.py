from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base
from data_platform.extractors.incremental_cc_extractor import (
    PIPELINE_NAME,
    CommonCrawlCheckpoint,
    IncrementalCCStats,
    IncrementalCommonCrawlExtractor,
)
from db.models import PipelineState


def test_common_crawl_missing_indices_are_recent_first_with_lookback() -> None:
    indices = [
        "CC-MAIN-2026-27",
        "CC-MAIN-2026-22",
        "CC-MAIN-2026-18",
        "CC-MAIN-2026-13",
        "CC-MAIN-2025-08",
    ]
    checkpoint = CommonCrawlCheckpoint(
        last_completed_index=None,
        completed_indices=frozenset({"CC-MAIN-2026-27"}),
    )

    missing = IncrementalCommonCrawlExtractor._compute_missing_indices(
        indices,
        checkpoint=checkpoint,
        lookback_indices=3,
    )

    assert missing == ["CC-MAIN-2026-22", "CC-MAIN-2026-18"]


def test_common_crawl_legacy_checkpoint_marks_older_indices_complete() -> None:
    indices = [
        "CC-MAIN-2026-27",
        "CC-MAIN-2026-22",
        "CC-MAIN-2026-18",
        "CC-MAIN-2025-08",
        "CC-MAIN-2024-51",
    ]

    checkpoint = IncrementalCommonCrawlExtractor._checkpoint_from_state(
        {"last_completed_index": "CC-MAIN-2026-18"},
        all_indices=indices,
    )

    assert "CC-MAIN-2026-18" in checkpoint.completed_indices
    assert "CC-MAIN-2025-08" in checkpoint.completed_indices
    assert "CC-MAIN-2026-22" not in checkpoint.completed_indices


def test_common_crawl_checkpoint_preserves_incomplete_metadata() -> None:
    checkpoint = IncrementalCommonCrawlExtractor._checkpoint_from_state(
        {
            "completed_indices": ["CC-MAIN-2026-18"],
            "failed_indices": ["CC-MAIN-2026-22"],
            "timed_out_indices": ["CC-MAIN-2026-27"],
        },
        all_indices=[
            "CC-MAIN-2026-27",
            "CC-MAIN-2026-22",
            "CC-MAIN-2026-18",
            "CC-MAIN-2025-08",
        ],
    )

    assert "CC-MAIN-2026-18" in checkpoint.completed_indices
    assert "CC-MAIN-2026-22" in checkpoint.failed_indices
    assert "CC-MAIN-2026-27" in checkpoint.timed_out_indices
    assert "CC-MAIN-2026-27" not in checkpoint.completed_indices


@pytest.mark.asyncio
async def test_common_crawl_incomplete_index_is_not_completed() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as session:
        await IncrementalCommonCrawlExtractor._record_incomplete_index(
            session,
            "CC-MAIN-2026-27",
            reason="timed_out",
        )
        row = await session.scalar(
            select(PipelineState).where(PipelineState.pipeline_name == PIPELINE_NAME)
        )

    await engine.dispose()

    assert row is not None
    assert row.state_data["completed_indices"] == []
    assert row.state_data["timed_out_indices"] == ["CC-MAIN-2026-27"]
    assert row.state_data["incomplete_attempts"][0]["reason"] == "timed_out"


@pytest.mark.asyncio
async def test_common_crawl_index_retry_helper_retries_before_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = IncrementalCommonCrawlExtractor(
        max_index_attempts=3,
        index_retry_backoff_seconds=0,
    )
    calls = 0

    async def flaky_process(*_args: object) -> list[dict[str, object]]:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("temporary index outage")
        return [{"url": "https://example.test", "text": "ok"}]

    monkeypatch.setattr(extractor, "_process_single_index", flaky_process)

    result = await extractor._process_single_index_with_retries(
        "CC-MAIN-2026-27",
        IncrementalCCStats(),
        0.0,
    )

    assert calls == 3
    assert result == [{"url": "https://example.test", "text": "ok"}]


@pytest.mark.asyncio
async def test_warc_requests_retry_transient_responses_before_returning_success() -> None:
    extractor = IncrementalCommonCrawlExtractor(
        warc_max_retries=3,
        warc_retry_delay_seconds=0,
    )
    request = httpx.Request("GET", "https://data.commoncrawl.org/example.warc.gz")

    class FlakyClient:
        def __init__(self) -> None:
            self.calls = 0

        async def get(self, _url: str, *, headers: dict[str, str]) -> httpx.Response:
            assert headers["Range"] == "bytes=0-10"
            self.calls += 1
            status_code = 503 if self.calls < 3 else 206
            return httpx.Response(status_code, request=request)

    client = FlakyClient()
    response = await extractor._request_warc_range(
        client,  # type: ignore[arg-type]
        str(request.url),
        {"Range": "bytes=0-10"},
    )

    assert response.status_code == 206
    assert client.calls == 3
