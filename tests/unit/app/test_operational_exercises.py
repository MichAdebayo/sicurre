"""Controlled operational exercise behavior and authorization tests."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from core.config import Settings
from core.operational_exercises import OperationalExerciseManager
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
    assert "INSERT INTO app_operational_exercise" in queries[0][0]

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
