"""Run the scheduled SEKOIA Community IOC ingestion delegate.

Forces R2 storage under cron/scraping/sekoia_ioc/ prefix.
Pass --reserved to write under cron/reserved/scraping/sekoia_ioc/ instead.
"""

from __future__ import annotations

import argparse as _argparse
import asyncio
import logging
import os
import sys
from collections.abc import MutableMapping
from pathlib import Path

# Reserved-slot routing must happen before settings are loaded.
_parser = _argparse.ArgumentParser(add_help=False)
_parser.add_argument("--reserved", action="store_true", default=False)
_reserved_args, _ = _parser.parse_known_args()


def configure_snapshot_environment(environ: MutableMapping[str, str], *, reserved: bool) -> None:
    """Route scheduled snapshots to production or an approved POC namespace."""
    poc_mode = environ.get("SICURRE_POC_MODE", "false").lower() == "true"
    if poc_mode:
        environ["SICURRE_SEKOIA_SNAPSHOT_STORAGE_BACKEND"] = "local"
        poc_prefix = environ.get("SICURRE_POC_SNAPSHOT_PREFIX", "demonstrations/poc")
        environ["SICURRE_SEKOIA_SNAPSHOT_PREFIX"] = f"{poc_prefix}/scraping/sekoia_ioc"
        return
    environ["SICURRE_SEKOIA_SNAPSHOT_STORAGE_BACKEND"] = "prod"
    environ["SICURRE_SEKOIA_SNAPSHOT_PREFIX"] = (
        "cron/reserved/scraping/sekoia_ioc" if reserved else "cron/scraping/sekoia_ioc"
    )


configure_snapshot_environment(os.environ, reserved=_reserved_args.reserved)

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:  # pragma: no cover - direct-script compatibility
    sys.path.insert(0, str(SRC_ROOT))  # pragma: no cover

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import get_settings  # noqa: E402
from core.database import Base  # noqa: E402
from data_platform.extractors.sekoia_ioc import SekoiaIocIngestionService  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def run_ingestion(*, trigger_mode: str = "scheduled") -> object:
    settings = get_settings()
    engine = create_async_engine(settings.data_platform_database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    poc_snapshot_dir = os.environ.get("SICURRE_POC_SNAPSHOT_DIR")
    service = SekoiaIocIngestionService(
        snapshot_dir=Path(poc_snapshot_dir) if poc_snapshot_dir else None,
        snapshot_prefix=settings.sekoia_snapshot_prefix,
    )
    try:
        async with session_factory() as session:
            return await service.run(session, trigger_mode=trigger_mode)
    finally:
        await engine.dispose()


async def main() -> None:
    snapshot_prefix = os.environ["SICURRE_SEKOIA_SNAPSHOT_PREFIX"]
    snapshot_backend = os.environ["SICURRE_SEKOIA_SNAPSHOT_STORAGE_BACKEND"]
    logger.info(
        "Starting SEKOIA IOC cron (snapshot backend: %s, prefix: %s)",
        snapshot_backend,
        snapshot_prefix,
    )
    result = await run_ingestion(trigger_mode="scheduled")
    logger.info("SEKOIA IOC cron completed: %s", result)


if __name__ == "__main__":
    asyncio.run(main())
