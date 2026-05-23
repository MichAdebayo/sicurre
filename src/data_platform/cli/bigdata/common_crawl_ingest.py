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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest the latest Common Crawl snapshot into the Sicurre DB"
    )
    parser.add_argument(
        "--trigger",
        default="manual",
        choices=["manual", "scheduled"],
        help="Trigger mode written to the Common Crawl ingestion run.",
    )
    return parser.parse_args()


async def run_ingestion(*, trigger_mode: str = "manual") -> object:
    load_dotenv(ROOT_DIR / ".env", override=True)
    settings = get_settings()
    db_url = settings.data_platform_database_url
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
        result = await service.run(session, trigger_mode=trigger_mode)

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
    return result


async def main() -> None:
    args = parse_args()
    await run_ingestion(trigger_mode=args.trigger)


if __name__ == "__main__":
    asyncio.run(main())
