"""Tests for bounded load-audit aggregation and release gates."""

from __future__ import annotations

import httpx
import pytest
import respx

from data_platform.services.shared.load_audit import (
    LoadAuditConfig,
    LoadAuditResult,
    run_load_audit,
)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"url": "file:///tmp/test"}, "HTTP or HTTPS"),
        ({"request_count": 0}, "request_count"),
        ({"request_count": 5, "concurrency": 6}, "concurrency"),
        ({"timeout_seconds": 0}, "timeout_seconds"),
    ],
)
def test_config_rejects_unbounded_inputs(override: dict[str, object], message: str) -> None:
    values: dict[str, object] = {"url": "https://api.example.test/health"}
    values.update(override)
    with pytest.raises(ValueError, match=message):
        LoadAuditConfig(**values)  # type: ignore[arg-type]


def test_result_uses_nearest_rank_and_explicit_gates() -> None:
    result = LoadAuditResult(
        request_count=5,
        success_count=4,
        duration_seconds=2,
        latencies_ms=(10, 20, 30, 40),
        status_counts={"200": 4, "503": 1},
    )
    assert result.error_count == 1
    assert result.error_rate == 0.2
    assert result.throughput_per_second == 2.5
    assert result.average_ms == 25
    assert result.percentile_ms(50) == 20
    assert result.percentile_ms(95) == 40
    assert result.meets(max_error_rate=0.2, max_p95_ms=40)
    assert not result.meets(max_error_rate=0.1, max_p95_ms=40)


@respx.mock
@pytest.mark.asyncio
async def test_run_counts_expected_status_and_bounded_http_failure() -> None:
    route = respx.get("https://api.example.test/health")
    route.side_effect = [
        httpx.Response(200),
        httpx.Response(503),
        httpx.ConnectError("offline"),
    ]
    result = await run_load_audit(
        LoadAuditConfig(
            url="https://api.example.test/health",
            request_count=3,
            concurrency=1,
        )
    )
    assert result.success_count == 1
    assert result.status_counts == {"200": 1, "503": 1, "error:ConnectError": 1}
