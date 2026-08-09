"""Run the daily global quarantine-retention purge."""

from __future__ import annotations

import asyncio
import logging

from core.config import get_settings
from data_platform.api.auth import async_query
from data_platform.services.quarantine_retention import purge_expired_quarantine
from data_platform.services.quarantine_storage import build_quarantine_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Purge all expired held messages and fail when custody deletion is incomplete."""
    settings = get_settings()
    result = await purge_expired_quarantine(
        query=async_query,
        store=build_quarantine_store(settings),
    )
    logger.info(
        "Quarantine purge complete: candidates=%d purged=%d failed=%d",
        result.candidates,
        result.purged,
        result.failed,
    )
    if result.failed:
        raise RuntimeError(f"Failed to purge {result.failed} quarantine object(s)")


if __name__ == "__main__":
    asyncio.run(main())
