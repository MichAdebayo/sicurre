"""Admin-only synthetic monitoring exercises with a persisted audit trail."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.config import get_settings
from core.operational_exercises import (
    EXERCISE_TYPES,
    OperationalExercise,
    log_exercise_event,
    operational_exercises,
)
from core.rate_limit import limiter
from data_platform.api.auth import AuthUser, get_current_user
from data_platform.api.schemas.app_responses import (
    OperationalExerciseResponse,
    OperationalExerciseStateResponse,
)
from db.runtime import execute_runtime_query

router = APIRouter(tags=["app-ui-flows"])


class OperationalExerciseCreate(BaseModel):
    """Validated request for one bounded monitoring exercise."""

    exercise_type: str = Field(pattern="^(api_unavailable|high_latency|elevated_5xx)$")
    duration_seconds: int = Field(default=240, ge=120, le=1800)


_operational_background_tasks: set[asyncio.Task[None]] = set()


async def _persist_exercise_recovery(exercise_id: str, recovered_at: str) -> None:
    """Persist once; a manual recovery must not later be logged as automatic."""
    changed = await execute_runtime_query(
        "UPDATE app_operational_exercise SET status = ?, recovered_at = ? "
        "WHERE id = ? AND status = 'active' RETURNING id, exercise_type",
        ("recovered", recovered_at, exercise_id),
    )
    if changed:
        log_exercise_event(
            message="Operational exercise expired",
            event="operational_exercise_recovered",
            exercise_id=exercise_id,
            exercise_type=changed[0]["exercise_type"],
            actor_id="system",
            recovery_mode="automatic",
        )


async def synchronize_operational_exercises() -> None:
    """Reconcile persisted exercises after expiry or an API process restart."""
    rows = await execute_runtime_query(
        "SELECT id, exercise_type, initiated_by, started_at, expires_at, status "
        "FROM app_operational_exercise WHERE status = 'active' ORDER BY started_at DESC"
    )
    now = datetime.now(UTC)
    for row in rows:
        if row.get("status") != "active":
            continue
        remaining = (datetime.fromisoformat(row["expires_at"]) - now).total_seconds()
        if remaining <= 0:
            await _persist_exercise_recovery(row["id"], row["expires_at"])
        elif operational_exercises.current() is None:
            operational_exercises.restore(
                OperationalExercise(
                    id=row["id"],
                    exercise_type=row["exercise_type"],
                    initiated_by=row["initiated_by"],
                    started_at=row["started_at"],
                    expires_at=row["expires_at"],
                )
            )
            task = asyncio.create_task(_mark_exercise_recovered(row["id"], remaining))
            _operational_background_tasks.add(task)
            task.add_done_callback(_operational_background_tasks.discard)


async def _mark_exercise_recovered(exercise_id: str, duration_seconds: float) -> None:
    """Persist automatic recovery after the synthetic signal expires."""
    await asyncio.sleep(duration_seconds + 1)
    recovered_at = datetime.now(UTC).isoformat()
    await _persist_exercise_recovery(exercise_id, recovered_at)


@router.get(
    "/v1/admin/operational-exercises",
    response_model=OperationalExerciseStateResponse,
    response_model_exclude_unset=True,
)
async def get_operational_exercises(current_user: AuthUser = Depends(get_current_user)):
    """Return active state and recent audit records for platform administrators."""
    if not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Platform admin access required")
    await synchronize_operational_exercises()
    rows = await execute_runtime_query(
        "SELECT id, exercise_type, status, initiated_by, started_at, expires_at, recovered_at "
        "FROM app_operational_exercise ORDER BY started_at DESC LIMIT 10"
    )
    return {
        "enabled": get_settings().operational_tests_enabled,
        "active": operational_exercises.current(),
        "recent": rows,
        "supported_types": sorted(EXERCISE_TYPES),
    }


@router.post(
    "/v1/admin/operational-exercises",
    status_code=201,
    response_model=OperationalExerciseResponse,
    response_model_exclude_unset=True,
)
@limiter.limit("2/hour")
async def start_operational_exercise(
    request: Request,
    payload: OperationalExerciseCreate,
    current_user: AuthUser = Depends(get_current_user),
):
    """Start one admin-only synthetic signal without affecting customer traffic."""
    del request
    if not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Platform admin access required")
    settings = get_settings()
    if not settings.operational_tests_enabled:
        raise HTTPException(status_code=409, detail="Operational exercises are disabled")
    if payload.duration_seconds > settings.operational_test_max_duration_seconds:
        raise HTTPException(
            status_code=422, detail="Exercise duration exceeds the configured limit"
        )

    await synchronize_operational_exercises()
    exercise_id = str(uuid.uuid4())
    try:
        active = operational_exercises.start(
            exercise_id=exercise_id,
            exercise_type=payload.exercise_type,
            initiated_by=current_user.email,
            duration_seconds=payload.duration_seconds,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        await execute_runtime_query(
            "INSERT INTO app_operational_exercise "
            "(id, exercise_type, status, initiated_by, started_at, expires_at, recovered_at) "
            "VALUES (?, ?, 'active', ?, ?, ?, NULL)",
            (
                active["id"],
                active["exercise_type"],
                active["initiated_by"],
                active["started_at"],
                active["expires_at"],
            ),
        )
    except Exception:
        operational_exercises.recover(exercise_id)
        raise
    recovery_task = asyncio.create_task(
        _mark_exercise_recovered(exercise_id, payload.duration_seconds)
    )
    _operational_background_tasks.add(recovery_task)
    recovery_task.add_done_callback(_operational_background_tasks.discard)
    log_exercise_event(
        message="Controlled operational exercise started",
        event="operational_exercise_started",
        exercise_id=exercise_id,
        exercise_type=payload.exercise_type,
        actor_id=current_user.id,
    )
    return active


@router.post(
    "/v1/admin/operational-exercises/{exercise_id}/recover",
    response_model=OperationalExerciseResponse,
    response_model_exclude_unset=True,
)
@limiter.limit("6/hour")
async def recover_operational_exercise(
    request: Request,
    exercise_id: str,
    current_user: AuthUser = Depends(get_current_user),
):
    """Recover an active exercise early and preserve its audit trail."""
    del request
    if not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Platform admin access required")
    await synchronize_operational_exercises()
    recovered = operational_exercises.current()
    if recovered is None or recovered["id"] != exercise_id:
        raise HTTPException(status_code=404, detail="Active operational exercise not found")
    recovered_at = datetime.now(timezone.utc).isoformat()
    await execute_runtime_query(
        "UPDATE app_operational_exercise SET status = ?, recovered_at = ? WHERE id = ?",
        ("recovered", recovered_at, exercise_id),
    )
    operational_exercises.recover(exercise_id)
    log_exercise_event(
        message="Controlled operational exercise recovered",
        event="operational_exercise_recovered",
        exercise_id=exercise_id,
        exercise_type=recovered["exercise_type"],
        actor_id=current_user.id,
        recovery_mode="manual",
    )
    return {**recovered, "status": "recovered", "recovered_at": recovered_at}
