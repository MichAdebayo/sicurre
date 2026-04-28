"""Run the scheduled Common Crawl big-data pipeline incrementally to the cron output dir."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Force the ingestion service to write its final snapshot to R2 under the cron/ prefix
os.environ["SICURRE_COMMON_CRAWL_SNAPSHOT_STORAGE_BACKEND"] = "prod"
os.environ["SICURRE_COMMON_CRAWL_SNAPSHOT_PREFIX"] = "cron/bigdata/common_crawl"

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.config import get_settings
from data_platform.cli.bigdata.common_crawl_extract import build_settings, run_extraction
from data_platform.cli.bigdata.common_crawl_ingest import run_ingestion
from data_platform.extractors.common_crawl_ingestion import LocalCommonCrawlClient, CommonCrawlIngestionService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the scheduled Common Crawl extract→ingest delegate."
    )
    return parser.parse_args()


def build_scheduled_args() -> argparse.Namespace:
    return argparse.Namespace(
        trigger="scheduled",
        skip_extract=False,
        skip_ingest=False,
        max_results_per_query=80,
        max_warc_downloads=80,
        target_records=50,
        async_concurrency=6,
        min_text_length=None,
        max_text_length=None,
        request_timeout=15,
        batch_size=20,
        query_profile="phishing-refresh",
        fallback_mode="none",
        recovery_parquet_count=1,
        log_level="INFO",
        cc_snapshot_dir=None,  # We will override this dynamically
    )


async def run_incremental_common_crawl_cron() -> None:
    now = datetime.now(timezone.utc)
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")
    cron_dir = ROOT_DIR / "data" / "raw-snapshots" / "cron" / "bigdata" / "common_crawl" / timestamp_str
    
    logger.info("Starting isolated Common Crawl cron run. Target dir: %s", cron_dir)
    
    # 1. Extraction
    args = build_scheduled_args()
    # Override snapshot dir so extraction saves to our cron folder
    args.cc_snapshot_dir = str(cron_dir)
    
    settings = build_settings(args)
    try:
        extraction_result = await run_extraction(
            settings=settings,
            query_profile="phishing-refresh",
        )
    except Exception as exc:
        logger.error("Live Common Crawl extraction failed: %s", exc)
        sys.exit(1)

    logger.info("Extraction complete. Extracted %d records.", extraction_result.raw_count)
    if extraction_result.usable_french_count == 0:
        logger.info("No usable French records found. Cron exiting cleanly.")
        return

    # 2. Ingestion
    # We must enforce Local mode and point it directly to the cron directory
    os.environ["CC_INPUT_BACKEND"] = "local"
    
    # Force the local client to read from the folder we just wrote to
    fr_usable_dir = Path(extraction_result.artifacts.fr_usable_storage_uri).parent
    
    local_client = LocalCommonCrawlClient(local_parquet_dir=fr_usable_dir)
    ingestion_service = CommonCrawlIngestionService(bq_client=local_client)
    
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    engine = create_async_engine(get_settings().database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    
    async with session_factory() as session:
        result = await ingestion_service.run(session, trigger_mode="scheduled")
        
    logger.info("Ingestion completed: %s", result.log_message)
    await engine.dispose()


if __name__ == "__main__":
    parse_args()
    asyncio.run(run_incremental_common_crawl_cron())
