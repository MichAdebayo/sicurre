"""Run the scheduled CERT-FR CTI ingestion delegate.

Forces R2 storage under cron/scraping/certfr_cti/ prefix.
Pass --reserved to write under cron/reserved/scraping/certfr_cti/ instead.
"""

from __future__ import annotations

import argparse as _argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# ── Reserved-slot routing (must happen before settings are loaded) ─────────────
_parser = _argparse.ArgumentParser(add_help=False)
_parser.add_argument("--reserved", action="store_true", default=False)
_reserved_args, _ = _parser.parse_known_args()

# Force snapshot storage to R2 under the appropriate cron prefix
os.environ["SICURRE_CERTFR_SNAPSHOT_STORAGE_BACKEND"] = "prod"
os.environ["SICURRE_CERTFR_SNAPSHOT_PREFIX"] = (
    "cron/reserved/scraping/certfr_cti"
    if _reserved_args.reserved
    else "cron/scraping/certfr_cti"
)
# ──────────────────────────────────────────────────────────────────────────────

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import get_settings
from core.database import Base
from data_platform.extractors.certfr_cti import CertFRCtiExtractor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def run_ingestion(
    *,
    trigger_mode: str = "scheduled",
    fetch_historical: bool = False,
) -> object:
    settings = get_settings()
    engine = create_async_engine(settings.data_platform_database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    extractor = CertFRCtiExtractor(
        snapshot_prefix=settings.certfr_snapshot_prefix
    )
    try:
        async with session_factory() as session:
            return await extractor.run(
                session,
                trigger_mode=trigger_mode,
                fetch_historical=fetch_historical,
            )
    finally:
        await engine.dispose()


async def main() -> None:
    _r2_prefix = os.environ["SICURRE_CERTFR_SNAPSHOT_PREFIX"]
    logger.info("Starting CERT-FR CTI cron (R2 target: %s)", _r2_prefix)
    await run_ingestion(trigger_mode="scheduled", fetch_historical=False)


if __name__ == "__main__":
    asyncio.run(main())
