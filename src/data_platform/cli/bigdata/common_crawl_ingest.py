from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

load_dotenv(ROOT_DIR / ".env")

from core.config import get_settings  # noqa: E402
from core.database import Base  # noqa: E402
from data_platform.extractors.common_crawl_ingestion import (  # noqa: E402
    CommonCrawlIngestionService,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    db_url = settings.database_url
    logger.info("Using Sicurre main database: %s", db_url)

    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Tables ensured on Sicurre DB")

    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    service = CommonCrawlIngestionService()

    async with session_factory() as session:
        result = await service.run(session, trigger_mode="manual")

    print("=====================================================")
    print(result.log_message or "Big Data Common Crawl ingestion completed")
    print("=====================================================")
    print(
        f"  Total Processed BigQuery: {result.total_extracted_count}\n"
        f"  New Records Saved:      {result.raw_record_count}\n"
        f"  Skipped (Existing):     {result.skipped_count}\n"
        f"  Snapshot Extracted:     {result.raw_object_count}"
    )
    if result.snapshot_storage_uri:
        print(f"  Snapshot URI:           {result.snapshot_storage_uri}")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Manually ingest the latest Common Crawl R2 snapshot via BigQuery"
    )
    parser.parse_args()
    asyncio.run(main())
