"""Periodic database ping that keeps the connection pool warm.

On a serverless PostgreSQL (Neon) a scan would otherwise pay connection
establishment, and possibly a compute wake, inside the two-second budget.
The loop runs until cancelled, records each result through ``core.db_health``,
and never raises into the caller: a failed ping is logged and retried at the
next interval. It is not a health check.

Enabled only for a PostgreSQL URL and when ``SICURRE_DB_KEEPALIVE_ENABLED``
is true (see ``keepalive_enabled``). Rationale and measurements: ADR-0004.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from core.config import get_settings
from core.db_health import record_failure, record_success
from db.runtime import get_app_engine

logger = logging.getLogger(__name__)

# Under Neon's idle-suspend window.
DEFAULT_INTERVAL_SECONDS = 30.0


async def _ping_once() -> None:
    engine = get_app_engine()
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def check_database_now() -> None:
    """Probe the database once and record the result.

    Used by the readiness endpoint when no recent observation exists, which is
    the case whenever the keepalive is turned off. It raises on failure so the
    caller can record the reason.
    """
    await _ping_once()
    record_success()


async def run_db_keepalive(interval_seconds: float | None = None) -> None:
    """Ping the database on an interval until cancelled."""
    interval = interval_seconds or DEFAULT_INTERVAL_SECONDS
    while True:
        try:
            await _ping_once()
            # The ping already proves the database answered. Recording that is
            # free, and it is the only regular observation this service makes.
            record_success()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - warmth is best-effort by design
            record_failure(f"{type(exc).__name__}: {exc}")
            logger.warning("Database keepalive ping failed: %s", exc)
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise


def keepalive_enabled() -> bool:
    """Return True when a keepalive should run.

    Requires a PostgreSQL ``database_url`` and ``db_keepalive_enabled``; local
    SQLite never needs one. The switch exists because the ping also stops a
    metered serverless compute from suspending.
    """
    settings = get_settings()
    if not settings.db_keepalive_enabled:
        return False
    return (settings.database_url or "").startswith("postgresql")
