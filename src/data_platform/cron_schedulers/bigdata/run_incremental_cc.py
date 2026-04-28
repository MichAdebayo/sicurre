"""Run the resumable, time-bounded Common Crawl cron pipeline.

Forces R2 storage under cron/bigdata/common_crawl/ prefix.
Duration is controlled by SICURRE_CC_CRON_DURATION_MODE:
  - 'short'    → 30 minutes (for demos / jury)
  - 'standard' → 8 hours    (for overnight runs)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# Force snapshot storage to R2 under the cron/bigdata/common_crawl prefix
os.environ["SICURRE_COMMON_CRAWL_SNAPSHOT_STORAGE_BACKEND"] = "prod"
os.environ["SICURRE_COMMON_CRAWL_SNAPSHOT_PREFIX"] = "cron/bigdata/common_crawl"

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import get_settings
from core.database import Base
from data_platform.extractors.incremental_cc_extractor import (
    DURATION_MAP,
    IncrementalCommonCrawlExtractor,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def run_incremental_cc_cron() -> None:
    settings = get_settings()
    duration_mode = settings.cc_cron_duration_mode.strip().lower()
    max_runtime = DURATION_MAP.get(duration_mode)

    if max_runtime is None:
        logger.error(
            "Invalid CC_CRON_DURATION_MODE: '%s'. Must be 'short' or 'standard'.",
            duration_mode,
        )
        raise SystemExit(1)

    logger.info(
        "CC Cron duration mode: %s (%d minutes)",
        duration_mode,
        max_runtime // 60,
    )

    engine = create_async_engine(settings.database_url, echo=False)

    # Ensure the pipeline_state table exists
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    extractor = IncrementalCommonCrawlExtractor(max_runtime_seconds=max_runtime)

    async with session_factory() as session:
        result = await extractor.run(session)

    logger.info("--- CC Cron Summary ---")
    logger.info("Indices attempted: %s", result.indices_attempted)
    logger.info("Indices completed: %s", result.indices_completed)
    logger.info("Total extracted:   %d", result.total_extracted)
    logger.info("Timed out:         %s", result.timed_out)
    logger.info("R2 URIs:           %s", result.r2_uris)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_incremental_cc_cron())
