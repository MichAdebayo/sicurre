import argparse
import asyncio
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from core.config import settings
from data_platform.services.normalization_pipeline import NormalizationPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
logger = logging.getLogger(__name__)

async def main():
    parser = argparse.ArgumentParser(description="Sicurre DB Normalization Pipeline (Phase 2)")
    parser.add_argument("--batch-size", type=int, default=1000, help="Number of records to process")
    parser.add_argument("--source", type=str, default=None, help="Filter by specific source system name")
    parser.add_argument("--dry-run", action="store_true", help="Print extraction results without commiting SQL")
    args = parser.parse_args()

    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    logger.info(f"Connecting to database: {settings.SQLALCHEMY_DATABASE_URI}")
    
    async with session_maker() as session:
        pipeline = NormalizationPipeline(session)
        result = await pipeline.run_batch(
            batch_size=args.batch_size,
            source_system_name=args.source,
            dry_run=args.dry_run
        )
        
        if args.dry_run:
            logger.info("--- DRY RUN SAMPLES ---")
            for sample in result.get("samples", []):
                logger.info(f"Source: {sample['source']}")
                logger.info(f"Label: {sample['extracted_label']}")
                logger.info(f"Text Preview: {sample['text_sample']}")
                logger.info("-" * 40)
            logger.info(f"Total processed in dry run: {result.get('processed')}")
        else:
            logger.info(f"Execution complete: {result}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
