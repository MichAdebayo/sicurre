"""A health check that survives its database being gone is not a health check.

Production Neon exhausted its compute quota and suspended. Every request that
touched the database failed for over an hour, and `/health` went on returning
`{"status": "ok"}` throughout, because it returned a hardcoded string. The
outage was found by hand.

The fix is not to make `/health` query the database. Docker restarts this
container when `/health` fails, and restarting cannot reach a database that is
down — it loops and buries the cause. Liveness and readiness are separated:
`/health` says the process is up, `/health/ready` says whether it can serve.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from core import db_health


@pytest.fixture(autouse=True)
def _clean_state():
    db_health.reset_for_tests()
    yield
    db_health.reset_for_tests()


@pytest.fixture
def client():
    from data_platform.api.main import app

    return TestClient(app, raise_server_exceptions=False)


def test_liveness_stays_up_when_the_database_is_gone(client, monkeypatch) -> None:
    """The regression that matters: a dead database must not restart the API.

    Docker's healthcheck polls /health every 30s and recreates the container
    after five failures. Coupling it to the database turns an outage into a
    restart loop that hides the outage.
    """
    db_health.record_failure("OperationalError: compute quota exceeded")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_reports_a_database_that_is_gone(client) -> None:
    """What /health could not say, and what would have caught the outage."""
    db_health.record_failure("OperationalError: compute time quota exceeded")

    response = client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "unreachable"
    assert "quota" in body["detail"], "the reason must survive to the caller"


def test_readiness_reports_a_healthy_database(client) -> None:
    db_health.record_success()

    response = client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database"] == "reachable"
    assert body["detail"] is None
    assert body["observed_seconds_ago"] < 5


def test_a_stale_observation_triggers_a_fresh_probe(client, monkeypatch) -> None:
    """With the keepalive off nothing refreshes the record, so readiness looks."""
    from data_platform.api import main

    db_health.record_success()
    db_health._state["at"] = time.time() - (db_health.STALE_AFTER_SECONDS + 10)

    probed: list[bool] = []

    async def probe() -> None:
        probed.append(True)
        db_health.record_success()

    monkeypatch.setattr(main, "check_database_now", probe)

    response = client.get("/health/ready")

    assert probed == [True], "a stale record must be refreshed, not served"
    assert response.status_code == 200


def test_a_fresh_observation_is_served_without_probing(client, monkeypatch) -> None:
    """Scraping readiness must not add load, nor hold a serverless compute awake."""
    from data_platform.api import main

    db_health.record_success()

    async def probe() -> None:
        raise AssertionError("a fresh observation must not trigger a probe")

    monkeypatch.setattr(main, "check_database_now", probe)

    assert client.get("/health/ready").status_code == 200


def test_a_failing_probe_becomes_the_answer(client, monkeypatch) -> None:
    """An unreachable database is the result, not a 500."""
    from data_platform.api import main

    async def probe() -> None:
        raise OSError("connection refused")

    monkeypatch.setattr(main, "check_database_now", probe)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert "connection refused" in response.json()["detail"]


def test_nothing_observed_yet_is_not_reported_as_healthy(client, monkeypatch) -> None:
    """Silence is not success — the bug this whole endpoint exists to prevent."""
    from data_platform.api import main

    async def probe() -> None:
        raise TimeoutError("no answer")

    monkeypatch.setattr(main, "check_database_now", probe)

    assert client.get("/health/ready").status_code == 503


def test_the_keepalive_records_what_it_sees(monkeypatch) -> None:
    """The observation is free: the keepalive already opens a connection.

    A second periodic probe would be one more thing holding a serverless
    compute awake, which is the fault that caused the outage in the first place.
    """
    import asyncio

    from core import db_keepalive

    async def ping_ok() -> None:
        return None

    monkeypatch.setattr(db_keepalive, "_ping_once", ping_ok)
    asyncio.run(db_keepalive.check_database_now())

    ok_flag, detail, age = db_health.last_observation()
    assert ok_flag is True
    assert detail is None
    assert age is not None and age < 5
