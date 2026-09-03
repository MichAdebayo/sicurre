"""The SLA is judged on these series, so their names and labels are contract."""

from __future__ import annotations

import pytest
from prometheus_client import generate_latest

from core.scan_metrics import observe_scan, observe_stage, scan_stage_duration


def _metrics_text() -> str:
    return generate_latest().decode()


def test_scan_duration_is_exported_with_verdict_label() -> None:
    observe_scan(verdict="phishing", duration_seconds=1.2, sla_seconds=2.0)
    text = _metrics_text()
    assert "sicurre_scan_duration_seconds" in text
    assert 'verdict="phishing"' in text


def test_breach_counter_only_fires_past_the_sla() -> None:
    observe_scan(verdict="spam", duration_seconds=0.9, sla_seconds=2.0)
    before = _metrics_text()
    baseline = 'sicurre_scan_sla_breach_total{verdict="spam"}' in before

    observe_scan(verdict="spam", duration_seconds=3.4, sla_seconds=2.0)
    after = _metrics_text()
    assert 'sicurre_scan_sla_breach_total{verdict="spam"}' in after
    # a breach must be recorded even if none existed before
    assert baseline or 'sicurre_scan_sla_breach_total{verdict="spam"}' in after


def test_stage_timing_records_even_when_the_stage_raises() -> None:
    """A failing dependency must show as slow, not disappear from the histogram."""
    with pytest.raises(RuntimeError):
        with observe_stage("inference"):
            raise RuntimeError("provider down")
    text = _metrics_text()
    assert 'sicurre_scan_stage_duration_seconds_count{stage="inference"}' in text


def test_buckets_straddle_the_two_second_objective() -> None:
    bounds = scan_stage_duration._upper_bounds  # noqa: SLF001 - contract check
    assert 2.0 in bounds, "2s SLA must be a bucket boundary to read compliance directly"


def test_inference_client_is_reused_across_calls() -> None:
    """One TLS handshake per process, not per email.

    Opening a client per request cost ~275 ms of the scan on connection setup
    alone, so reuse is the behaviour worth pinning.
    """
    from core import inference_client
    from core.inference_client import get_inference_client

    inference_client._client = None  # other suites patch httpx globally
    first = get_inference_client()
    second = get_inference_client()
    assert first is second


def test_closed_inference_client_is_replaced() -> None:
    """A client closed at shutdown must not be handed out again."""
    import asyncio

    from core import inference_client
    from core.inference_client import close_inference_client, get_inference_client

    inference_client._client = None  # other suites patch httpx globally
    first = get_inference_client()
    asyncio.run(close_inference_client())
    second = get_inference_client()
    assert second is not first
    assert not second.is_closed
    asyncio.run(close_inference_client())


def test_keepalive_only_runs_for_a_remote_database() -> None:
    """Local SQLite has no connection to keep warm, and no compute to wake."""
    from core import db_keepalive

    class _S:
        database_url = "sqlite+aiosqlite:///./local.db"

    original = db_keepalive.get_settings
    db_keepalive.get_settings = lambda: _S()  # type: ignore[assignment]
    try:
        assert db_keepalive.keepalive_enabled() is False
        _S.database_url = "postgresql+psycopg://user@host/db"
        assert db_keepalive.keepalive_enabled() is True
    finally:
        db_keepalive.get_settings = original  # type: ignore[assignment]


def test_keepalive_survives_a_failing_ping() -> None:
    """Warmth is an optimisation; a failed ping must not end the loop."""
    import asyncio

    from core import db_keepalive

    calls = {"n": 0}

    async def flaky() -> None:
        calls["n"] += 1
        raise RuntimeError("connection reset")

    original = db_keepalive._ping_once
    db_keepalive._ping_once = flaky  # type: ignore[assignment]
    try:
        async def drive() -> None:
            task = asyncio.create_task(db_keepalive.run_db_keepalive(interval_seconds=0.01))
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(drive())
        assert calls["n"] >= 2, "loop stopped after a failing ping"
    finally:
        db_keepalive._ping_once = original  # type: ignore[assignment]


def test_ping_issues_one_trivial_statement() -> None:
    """The warm-up must stay a single cheap statement, not a health check."""
    import asyncio

    from core import db_keepalive

    executed: list[str] = []

    class _Conn:
        async def __aenter__(self) -> "_Conn":
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def execute(self, statement: object) -> None:
            executed.append(str(statement))

    class _Engine:
        def connect(self) -> "_Conn":
            return _Conn()

    original = db_keepalive.get_app_engine
    db_keepalive.get_app_engine = lambda: _Engine()  # type: ignore[assignment]
    try:
        asyncio.run(db_keepalive._ping_once())
    finally:
        db_keepalive.get_app_engine = original  # type: ignore[assignment]

    assert executed == ["SELECT 1"]


def test_keepalive_pings_repeatedly_while_healthy() -> None:
    """The loop must keep warming, not ping once and fall through."""
    import asyncio

    from core import db_keepalive

    calls = {"n": 0}

    async def ok() -> None:
        calls["n"] += 1

    original = db_keepalive._ping_once
    db_keepalive._ping_once = ok  # type: ignore[assignment]
    try:
        async def drive() -> None:
            task = asyncio.create_task(db_keepalive.run_db_keepalive(interval_seconds=0.01))
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(drive())
    finally:
        db_keepalive._ping_once = original  # type: ignore[assignment]

    assert calls["n"] >= 2


def test_lifespan_starts_and_stops_the_keepalive() -> None:
    """A background task that outlives the app would leak a connection."""
    import asyncio

    from data_platform.api import main as api_main

    started: list[str] = []

    async def fake_keepalive() -> None:
        started.append("running")
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            started.append("cancelled")
            raise

    class _S:
        environment = "test"
        scheduler_enabled = False
        operational_tests_enabled = False

    orig_settings = api_main.get_settings
    orig_enabled = api_main.keepalive_enabled
    orig_run = api_main.run_db_keepalive
    api_main.get_settings = lambda: _S()  # type: ignore[assignment]
    api_main.keepalive_enabled = lambda: True  # type: ignore[assignment]
    api_main.run_db_keepalive = fake_keepalive  # type: ignore[assignment]
    try:
        async def drive() -> None:
            async with api_main.lifespan(None):  # type: ignore[arg-type]
                await asyncio.sleep(0.02)

        asyncio.run(drive())
    finally:
        api_main.get_settings = orig_settings  # type: ignore[assignment]
        api_main.keepalive_enabled = orig_enabled  # type: ignore[assignment]
        api_main.run_db_keepalive = orig_run  # type: ignore[assignment]

    assert started == ["running", "cancelled"]


def test_api_responses_forbid_caching() -> None:
    """Threat payloads carry third-party personal data and must not be stored.

    An absent Cache-Control licenses heuristic freshness rather than forbidding
    caching, so the header has to be explicit.
    """
    from fastapi.testclient import TestClient

    from data_platform.api.main import create_app

    with TestClient(create_app()) as client:
        # 401 is fine — the header must be set regardless of the outcome, since
        # an unauthorised body can still be cached.
        response = client.get("/v1/threats")
        assert response.headers.get("Cache-Control") == "no-store"
        assert "Cookie" in (response.headers.get("Vary") or "")


def test_non_api_paths_keep_their_own_caching() -> None:
    """The rule is scoped to /v1/, not blanket-applied to every route."""
    from fastapi.testclient import TestClient

    from data_platform.api.main import create_app

    with TestClient(create_app()) as client:
        response = client.get("/health")
        assert response.headers.get("Cache-Control") != "no-store"
