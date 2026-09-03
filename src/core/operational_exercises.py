"""Bounded synthetic signals for administrator-run monitoring exercises."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock

from prometheus_client import Counter, Gauge

EXERCISE_TYPES = frozenset({"api_unavailable", "high_latency", "elevated_5xx"})

_active_signal = Gauge(
    "sicurre_operational_exercise_active",
    "Whether a bounded synthetic operational exercise is active.",
    ("exercise_type",),
)
_exercise_total = Counter(
    "sicurre_operational_exercises_total",
    "Controlled operational exercises started by type.",
    ("exercise_type",),
)
for _exercise_type in sorted(EXERCISE_TYPES):
    _active_signal.labels(exercise_type=_exercise_type).set(0)


@dataclass(frozen=True)
class OperationalExercise:
    """Public state for one active controlled exercise."""

    id: str
    exercise_type: str
    initiated_by: str
    started_at: str
    expires_at: str


class OperationalExerciseManager:
    """Maintain at most one automatically expiring synthetic signal."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._active: OperationalExercise | None = None
        self._recovery_task: asyncio.Task[None] | None = None

    def current(self) -> dict[str, str] | None:
        """Return the active exercise after clearing an expired signal."""
        with self._lock:
            if self._active and datetime.fromisoformat(self._active.expires_at) <= datetime.now(
                UTC
            ):
                self._clear_locked()
            return asdict(self._active) if self._active else None

    def start(
        self,
        *,
        exercise_id: str,
        exercise_type: str,
        initiated_by: str,
        duration_seconds: int,
    ) -> dict[str, str]:
        """Activate one fixed-cardinality signal and schedule its recovery."""
        if exercise_type not in EXERCISE_TYPES:
            raise ValueError("Unsupported operational exercise type")
        now = datetime.now(UTC)
        exercise = OperationalExercise(
            id=exercise_id,
            exercise_type=exercise_type,
            initiated_by=initiated_by,
            started_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=duration_seconds)).isoformat(),
        )
        with self._lock:
            if self._active is not None:
                raise RuntimeError("An operational exercise is already active")
            self._active = exercise
            _active_signal.labels(exercise_type=exercise_type).set(1)
            _exercise_total.labels(exercise_type=exercise_type).inc()
            self._recovery_task = asyncio.create_task(
                self._recover_after(exercise_id, duration_seconds)
            )
        return asdict(exercise)

    def restore(self, exercise: OperationalExercise) -> None:
        """Resume a persisted, unexpired signal without counting a new test."""
        remaining = (
            datetime.fromisoformat(exercise.expires_at) - datetime.now(UTC)
        ).total_seconds()
        if exercise.exercise_type not in EXERCISE_TYPES or remaining <= 0:
            return
        with self._lock:
            if self._active is not None:
                return
            self._active = exercise
            _active_signal.labels(exercise_type=exercise.exercise_type).set(1)
            self._recovery_task = asyncio.create_task(self._recover_after(exercise.id, remaining))

    def recover(self, exercise_id: str) -> dict[str, str] | None:
        """Clear an active exercise when its identifier matches."""
        with self._lock:
            if self._active is None or self._active.id != exercise_id:
                return None
            recovered = asdict(self._active)
            self._clear_locked()
            return recovered

    async def _recover_after(self, exercise_id: str, duration_seconds: float) -> None:
        await asyncio.sleep(duration_seconds)
        self.recover(exercise_id)

    def _clear_locked(self) -> None:
        if self._active:
            _active_signal.labels(exercise_type=self._active.exercise_type).set(0)
        self._active = None
        task = self._recovery_task
        self._recovery_task = None
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()


operational_exercises = OperationalExerciseManager()
