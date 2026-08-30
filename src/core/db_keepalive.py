"""Keep one database connection warm between scans.

Production Postgres is Neon: serverless, in another provider's region, reached
over TLS, and it suspends idle compute. Real traffic is roughly one email a
day, so by the time a scan arrives the pool is empty and the compute may be
asleep. The scan then pays connection establishment — and possibly a compute
wake — inside the latency budget the SLA is measured against.

Measurement: the database stage cost ~270 ms per scan across two round-trips on
a link whose round-trip time should be tens of milliseconds. That gap is setup,
not query time.

A small periodic query keeps a pooled connection open and the compute awake, so
the scan path finds a connection ready instead of building one. The cost is one
trivial statement per interval; the benefit is paid on every scan.

This is deliberately not a health check. It never raises into the caller and
never changes request behaviour — a failure is logged and the loop continues,
because a warm pool is an optimisation and must not become a failure mode.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from core.config import get_settings
from db.runtime import get_app_engine

logger = logging.getLogger(__name__)

# Comfortably under Neon's idle-suspend window while staying negligible in
# query volume: 120 pings an hour is nothing next to one scan a day.
DEFAULT_INTERVAL_SECONDS = 30.0


async def _ping_once() -> None:
    engine = get_app_engine()
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def run_db_keepalive(interval_seconds: float | None = None) -> None:
    """Ping the database on an interval until cancelled."""
    interval = interval_seconds or DEFAULT_INTERVAL_SECONDS
    while True:
        try:
            await _ping_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - warmth is best-effort by design
            logger.warning("Database keepalive ping failed: %s", exc)
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise


def keepalive_enabled() -> bool:
    """Only warm a real remote database; local SQLite has nothing to keep warm."""
    url = get_settings().database_url or ""
    return url.startswith("postgresql")
