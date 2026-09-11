"""Last known database reachability, for the readiness endpoint and a gauge.

Liveness (``/health``) never depends on the database: Docker restarts the
container on it, and a restart cannot fix an unreachable database. Readiness
reads the observation the keepalive ping records here; when no observation
is recent (``STALE_AFTER_SECONDS``) the readiness endpoint probes once.
"""

from __future__ import annotations

import time

from prometheus_client import Gauge

database_up = Gauge(
    "sicurre_database_up",
    "1 when the database last answered, 0 when it last refused.",
)
database_last_success = Gauge(
    "sicurre_database_last_success_timestamp_seconds",
    "Unix time of the last successful database round trip.",
)

# Nothing has been observed yet: neither reachable nor known-broken.
_state: dict[str, float | str | None] = {"at": None, "ok": None, "detail": None}

# Older than this and a caller wanting the truth has to go and look.
STALE_AFTER_SECONDS = 90.0


def record_success() -> None:
    """Note a database round trip that worked."""
    now = time.time()
    _state.update(at=now, ok=True, detail=None)
    database_up.set(1)
    database_last_success.set(now)


def record_failure(detail: str) -> None:
    """Note a database round trip that did not work, and why."""
    _state.update(at=time.time(), ok=False, detail=detail[:200])
    database_up.set(0)


def last_observation() -> tuple[bool | None, str | None, float | None]:
    """Return (ok, detail, age_seconds). `ok` is None when nothing is known."""
    at = _state["at"]
    age = None if at is None else time.time() - float(at)
    return _state["ok"], _state["detail"], age  # type: ignore[return-value]


def is_stale() -> bool:
    """True when the last observation is too old to answer with."""
    _, _, age = last_observation()
    return age is None or age > STALE_AFTER_SECONDS


def reset_for_tests() -> None:
    _state.update(at=None, ok=None, detail=None)
