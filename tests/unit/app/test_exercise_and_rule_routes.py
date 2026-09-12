"""Branch coverage for operational exercise and security rule routes driven directly."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import Request

from core.config import Settings
from core.operational_exercises import OperationalExerciseManager
from data_platform.api import workspace_scope
from data_platform.api.auth import AuthUser
from data_platform.api.routers import alerts, operational_exercises
from data_platform.api.routers.operational_exercises import OperationalExerciseCreate


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


def _settings(**overrides) -> Settings:
    values = {
        "operational_tests_enabled": True,
        "operational_test_max_duration_seconds": 600,
        **overrides,
    }
    return Settings(_env_file=None, **values)


@pytest.mark.asyncio
async def test_start_exercise_rejects_a_user_who_is_not_a_platform_admin() -> None:
    with pytest.raises(HTTPException) as exc:
        await operational_exercises.start_operational_exercise.__wrapped__(
            _request(),
            OperationalExerciseCreate(exercise_type="api_unavailable", duration_seconds=120),
            _user(admin=False),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_start_exercise_returns_conflict_when_the_feature_flag_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        operational_exercises, "get_settings", lambda: _settings(operational_tests_enabled=False)
    )
    with pytest.raises(HTTPException) as exc:
        await operational_exercises.start_operational_exercise.__wrapped__(
            _request(),
            OperationalExerciseCreate(exercise_type="high_latency", duration_seconds=120),
            _user(admin=True),
        )
    assert exc.value.status_code == 409
    assert exc.value.detail == "Operational exercises are disabled"


@pytest.mark.asyncio
async def test_start_exercise_rejects_a_duration_above_the_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        operational_exercises,
        "get_settings",
        lambda: _settings(operational_test_max_duration_seconds=120),
    )
    with pytest.raises(HTTPException) as exc:
        await operational_exercises.start_operational_exercise.__wrapped__(
            _request(),
            OperationalExerciseCreate(exercise_type="elevated_5xx", duration_seconds=300),
            _user(admin=True),
        )
    assert exc.value.status_code == 422
    assert exc.value.detail == "Exercise duration exceeds the configured limit"


@pytest.mark.asyncio
async def test_start_exercise_returns_conflict_when_another_exercise_is_already_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = OperationalExerciseManager()
    active = manager.start(
        exercise_id="running",
        exercise_type="api_unavailable",
        initiated_by="admin@example.test",
        duration_seconds=120,
    )
    queries: list[tuple[str, tuple]] = []

    async def query(sql: str, params: tuple = ()) -> list[dict]:
        queries.append((sql, params))
        return []

    async def no_wait(_exercise_id: str, _duration: int) -> None:
        return None

    monkeypatch.setattr(operational_exercises, "operational_exercises", manager)
    monkeypatch.setattr(operational_exercises, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)
    monkeypatch.setattr(operational_exercises, "_mark_exercise_recovered", no_wait)
    monkeypatch.setattr(operational_exercises, "get_settings", _settings)

    try:
        with pytest.raises(HTTPException) as exc:
            await operational_exercises.start_operational_exercise.__wrapped__(
                _request(),
                OperationalExerciseCreate(exercise_type="high_latency", duration_seconds=120),
                _user(admin=True),
            )
        assert exc.value.status_code == 409
        assert "already active" in exc.value.detail
        assert manager.current() == active
        assert not any(sql.startswith("INSERT") for sql, _ in queries)
    finally:
        manager.recover(active["id"])


@pytest.mark.asyncio
async def test_start_exercise_releases_the_signal_when_the_audit_insert_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = OperationalExerciseManager()
    queries: list[tuple[str, tuple]] = []

    async def query(sql: str, params: tuple = ()) -> list[dict]:
        queries.append((sql, params))
        if sql.startswith("INSERT INTO app_operational_exercise"):
            raise SQLAlchemyError("database unavailable")
        return []

    async def no_wait(_exercise_id: str, _duration: int) -> None:
        return None

    monkeypatch.setattr(operational_exercises, "operational_exercises", manager)
    monkeypatch.setattr(operational_exercises, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)
    monkeypatch.setattr(operational_exercises, "_mark_exercise_recovered", no_wait)
    monkeypatch.setattr(operational_exercises, "get_settings", _settings)

    with pytest.raises(SQLAlchemyError):
        await operational_exercises.start_operational_exercise.__wrapped__(
            _request(),
            OperationalExerciseCreate(exercise_type="api_unavailable", duration_seconds=120),
            _user(admin=True),
        )
    assert manager.current() is None
    assert any(sql.startswith("INSERT INTO app_operational_exercise") for sql, _ in queries)


@pytest.mark.asyncio
async def test_recover_exercise_rejects_a_user_who_is_not_a_platform_admin() -> None:
    with pytest.raises(HTTPException) as exc:
        await operational_exercises.recover_operational_exercise.__wrapped__(
            _request(), "exercise-1", _user(admin=False)
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_security_rule_returns_not_found_when_the_rule_does_not_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queries: list[tuple[str, tuple]] = []

    async def allow(_domain: str, _workspace_id: str) -> None:
        return None

    async def query(sql: str, params: tuple = ()) -> list[dict]:
        queries.append((sql, params))
        return []

    monkeypatch.setattr(workspace_scope, "require_workspace_domain", allow)
    monkeypatch.setattr(alerts, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    with pytest.raises(HTTPException) as exc:
        await alerts.delete_security_rule("rule-1", "Example.com", _user(admin=False))
    assert exc.value.status_code == 404
    assert exc.value.detail == "Rule not found"
    assert not any(sql.startswith("DELETE") for sql, _ in queries)


@pytest.mark.asyncio
async def test_delete_security_rule_removes_a_rule_scoped_to_the_workspace_and_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queries: list[tuple[str, tuple]] = []

    async def allow(_domain: str, _workspace_id: str) -> None:
        return None

    async def query(sql: str, params: tuple = ()) -> list[dict]:
        queries.append((sql, params))
        if sql.startswith("SELECT 1 FROM app_security_rule"):
            return [{"1": 1}]
        return []

    monkeypatch.setattr(workspace_scope, "require_workspace_domain", allow)
    monkeypatch.setattr(alerts, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await alerts.delete_security_rule("rule-1", " Example.COM ", _user(admin=False))
    assert result == {"status": "deleted"}
    deletes = [(sql, params) for sql, params in queries if sql.startswith("DELETE")]
    assert len(deletes) == 1
    sql, params = deletes[0]
    assert "DELETE FROM app_security_rule" in sql
    assert "workspace_id = ?" in sql
    assert "lower(domain) = lower(?)" in sql
    assert params == ("rule-1", "workspace-1", "example.com")
