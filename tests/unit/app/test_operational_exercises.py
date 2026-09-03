"""Controlled operational exercise behavior and authorization tests."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import Request

from core.config import Settings
from core.operational_exercises import OperationalExercise, OperationalExerciseManager
from data_platform.api import main as api_main
from data_platform.api.auth import AuthUser
from data_platform.api.main import create_app
from data_platform.api.routers import app_routes
from data_platform.api.routers.app_routes import OperationalExerciseCreate


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": []})


def _user(*, admin: bool) -> AuthUser:
    return AuthUser(
        id="owner-1",
        email="michael@sicurre.com",
        display_name="Michael",
        role="admin" if admin else "owner",
        workspace_id="workspace-1",
        workspace_name="Sicurre",
        is_platform_admin=admin,
    )


@pytest.mark.asyncio
async def test_manager_allows_one_exercise_and_recovers() -> None:
    manager = OperationalExerciseManager()
    active = manager.start(
        exercise_id="exercise-1",
        exercise_type="api_unavailable",
        initiated_by="owner@sicurre.com",
        duration_seconds=120,
    )
    assert active["exercise_type"] == "api_unavailable"
    with pytest.raises(RuntimeError, match="already active"):
        manager.start(
            exercise_id="exercise-2",
            exercise_type="high_latency",
            initiated_by="owner@sicurre.com",
            duration_seconds=120,
        )
    assert manager.recover("wrong-id") is None
    assert manager.recover("exercise-1") == active
    assert manager.current() is None

    with pytest.raises(ValueError, match="Unsupported"):
        manager.start(
            exercise_id="exercise-3",
            exercise_type="unknown",
            initiated_by="owner@sicurre.com",
            duration_seconds=120,
        )


@pytest.mark.asyncio
async def test_manager_clears_expired_and_automatic_signals(monkeypatch) -> None:
    manager = OperationalExerciseManager()
    expired = OperationalExercise(
        id="expired",
        exercise_type="high_latency",
        initiated_by="owner@sicurre.com",
        started_at=(datetime.now(UTC) - timedelta(minutes=2)).isoformat(),
        expires_at=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
    )
    manager._active = expired
    assert manager.current() is None

    manager._active = OperationalExercise(
        id="automatic",
        exercise_type="elevated_5xx",
        initiated_by="owner@sicurre.com",
        started_at=datetime.now(UTC).isoformat(),
        expires_at=(datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
    )

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("core.operational_exercises.asyncio.sleep", no_sleep)
    await manager._recover_after("automatic", 60)
    assert manager.current() is None


@pytest.mark.asyncio
async def test_operational_exercise_rejects_customer() -> None:
    with pytest.raises(HTTPException) as exc:
        await app_routes.start_operational_exercise.__wrapped__(
            _request(),
            OperationalExerciseCreate(exercise_type="elevated_5xx", duration_seconds=240),
            _user(admin=False),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_operational_exercise_requires_feature_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        app_routes,
        "get_settings",
        lambda: Settings(_env_file=None, operational_tests_enabled=False),
    )
    with pytest.raises(HTTPException) as exc:
        await app_routes.start_operational_exercise.__wrapped__(
            _request(),
            OperationalExerciseCreate(exercise_type="high_latency", duration_seconds=240),
            _user(admin=True),
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_admin_starts_and_recovers_audited_exercise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = OperationalExerciseManager()
    queries: list[tuple[str, tuple]] = []

    async def execute(sql: str, params: tuple = ()) -> list[dict]:
        queries.append((sql, params))
        return []

    async def no_wait(_exercise_id: str, _duration: int) -> None:
        return None

    monkeypatch.setattr(app_routes, "operational_exercises", manager)
    monkeypatch.setattr(app_routes, "execute_runtime_query", execute)
    monkeypatch.setattr(app_routes, "_mark_exercise_recovered", no_wait)
    monkeypatch.setattr(
        app_routes,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            operational_tests_enabled=True,
            operational_test_max_duration_seconds=600,
        ),
    )

    started = await app_routes.start_operational_exercise.__wrapped__(
        _request(),
        OperationalExerciseCreate(exercise_type="high_latency", duration_seconds=240),
        _user(admin=True),
    )
    await asyncio.sleep(0)
    assert started["exercise_type"] == "high_latency"
    assert any("INSERT INTO app_operational_exercise" in sql for sql, _ in queries)

    recovered = await app_routes.recover_operational_exercise.__wrapped__(
        _request(), started["id"], _user(admin=True)
    )
    assert recovered["status"] == "recovered"
    assert any("UPDATE app_operational_exercise" in sql for sql, _ in queries)


@pytest.mark.asyncio
async def test_operational_exercise_status_and_automatic_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [{"id": "exercise-1", "status": "recovered"}]
    queries: list[str] = []

    async def execute(sql: str, _params: tuple = ()) -> list[dict]:
        queries.append(sql)
        return rows if sql.startswith("SELECT") else []

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(app_routes, "execute_runtime_query", execute)
    monkeypatch.setattr(app_routes.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(
        app_routes,
        "get_settings",
        lambda: Settings(_env_file=None, operational_tests_enabled=True),
    )

    state = await app_routes.get_operational_exercises(_user(admin=True))
    assert state["enabled"] is True
    assert state["recent"] == rows
    await app_routes._mark_exercise_recovered("exercise-1", 120)
    assert any(sql.startswith("UPDATE app_operational_exercise") for sql in queries)

    with pytest.raises(HTTPException) as exc:
        await app_routes.get_operational_exercises(_user(admin=False))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_recovery_rejects_unknown_active_exercise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_routes, "operational_exercises", OperationalExerciseManager())

    async def no_rows(*_args):
        return []

    monkeypatch.setattr(app_routes, "execute_runtime_query", no_rows)
    with pytest.raises(HTTPException) as exc:
        await app_routes.recover_operational_exercise.__wrapped__(
            _request(), "missing", _user(admin=True)
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_operational_metric() -> None:
    app = create_app()
    endpoint = next(
        route.endpoint for route in app.routes if getattr(route, "path", None) == "/metrics"
    )
    response = await endpoint()
    assert b"sicurre_operational_exercise_active" in response.body


@pytest.mark.asyncio
async def test_restore_unexpired_exercise_after_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = OperationalExerciseManager()
    now = datetime.now(UTC)
    row = {
        "id": "restart-test",
        "exercise_type": "api_unavailable",
        "status": "active",
        "initiated_by": "admin@example.test",
        "started_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=120)).isoformat(),
    }

    async def execute(_sql, _params=()):
        return [row]

    monkeypatch.setattr(app_routes, "execute_runtime_query", execute)
    monkeypatch.setattr(app_routes, "operational_exercises", manager)
    await app_routes.synchronize_operational_exercises()
    assert manager.current()["id"] == row["id"]
    task = manager._recovery_task
    await app_routes.synchronize_operational_exercises()
    assert manager._recovery_task is task
    manager.recover(row["id"])
    for pending in tuple(app_routes._operational_background_tasks):
        pending.cancel()


@pytest.mark.asyncio
async def test_expired_persisted_exercise_is_closed_without_reactivation(monkeypatch) -> None:
    manager = OperationalExerciseManager()
    expired = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
    queries = []

    async def execute(sql, params=()):
        queries.append((sql, params))
        return (
            [{"id": "old", "status": "active", "expires_at": expired}]
            if sql.startswith("SELECT")
            else [{"id": "old"}]
        )

    monkeypatch.setattr(app_routes, "execute_runtime_query", execute)
    monkeypatch.setattr(app_routes, "operational_exercises", manager)
    await app_routes.synchronize_operational_exercises()
    assert manager.current() is None
    assert queries[-1][1] == ("recovered", expired, "old")


@pytest.mark.asyncio
async def test_automatic_recovery_does_not_log_a_second_manual_recovery(
    monkeypatch, caplog
) -> None:
    async def already_recovered(*_args):
        return []

    monkeypatch.setattr(app_routes, "execute_runtime_query", already_recovered)
    await app_routes._persist_exercise_recovery("manual", datetime.now(UTC).isoformat())
    assert "Operational exercise expired" not in caplog.text


@pytest.mark.asyncio
async def test_failed_recovery_write_keeps_signal_active(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = OperationalExerciseManager()
    active = manager.start(
        exercise_id="db-failure",
        exercise_type="api_unavailable",
        initiated_by="admin@example.test",
        duration_seconds=120,
    )

    async def execute(sql: str, _params: tuple = ()) -> list[dict]:
        if sql.startswith("UPDATE"):
            raise SQLAlchemyError("database unavailable")
        return []

    monkeypatch.setattr(app_routes, "operational_exercises", manager)
    monkeypatch.setattr(app_routes, "execute_runtime_query", execute)
    try:
        with pytest.raises(SQLAlchemyError):
            await app_routes.recover_operational_exercise.__wrapped__(
                _request(), active["id"], _user(admin=True)
            )
        assert manager.current() == active
    finally:
        manager.recover(active["id"])


@pytest.mark.asyncio
@pytest.mark.parametrize("exercise_type,seconds", [("unknown", 120), ("api_unavailable", -1)])
async def test_restore_ignores_invalid_or_expired_exercise(exercise_type: str, seconds: int) -> None:
    manager = OperationalExerciseManager()
    now = datetime.now(UTC)
    manager.restore(OperationalExercise(
        id="invalid", exercise_type=exercise_type, initiated_by="admin@example.test",
        started_at=now.isoformat(), expires_at=(now + timedelta(seconds=seconds)).isoformat(),
    ))
    assert manager.current() is None
    assert manager._recovery_task is None


@pytest.mark.asyncio
async def test_restore_does_not_replace_an_active_exercise() -> None:
    manager = OperationalExerciseManager()
    active = manager.start(
        exercise_id="existing", exercise_type="api_unavailable",
        initiated_by="admin@example.test", duration_seconds=120,
    )
    task = manager._recovery_task
    try:
        manager.restore(replace(OperationalExercise(**active), id="other"))
        assert manager.current() == active
        assert manager._recovery_task is task
    finally:
        manager.recover(active["id"])


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,db_failure", [(False, False), (True, False), (True, True)])
async def test_startup_restores_exercises_only_when_enabled_and_tolerates_database_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
    enabled: bool, db_failure: bool,
) -> None:
    settings = Settings(
        _env_file=None, environment="test", scheduler_enabled=False,
        operational_tests_enabled=enabled,
    )
    restore = AsyncMock(side_effect=SQLAlchemyError("private database detail") if db_failure else None)
    monkeypatch.setattr(api_main, "get_settings", lambda: settings)
    monkeypatch.setattr(api_main, "keepalive_enabled", lambda: False)
    monkeypatch.setattr(api_main, "synchronize_operational_exercises", restore)
    monkeypatch.setattr(api_main, "close_inference_client", AsyncMock())
    async with api_main.lifespan(None):
        assert restore.await_count == int(enabled)
    assert ("restoration deferred" in caplog.text) is db_failure
    assert "private database detail" not in caplog.text
