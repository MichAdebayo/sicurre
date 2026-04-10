"""Manually ingest records from the external legacy database source.

Usage::

    uv run python scripts/data_platform/historical_db/ingestion/ingest_legacy_db_source.py
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import get_settings  # noqa: E402
from core.database import Base  # noqa: E402
from data_platform.extractors.legacy_db import (  # noqa: E402
    LegacyDbIngestionService,
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

    service = LegacyDbIngestionService()

    async with session_factory() as session:
        result = await service.run(session, trigger_mode="manual")

    print(result.log_message or "DB ingestion completed")
    print(
        f"  new={result.raw_record_count}"
        f"  skipped={result.skipped_count}"
        f"  extracted={result.total_extracted_count}"
        f"  objects={result.raw_object_count}"
    )
    if result.snapshot_storage_uri:
        print(f"  snapshot={result.snapshot_storage_uri}")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="External Legacy Database Ingestion")
    args = parser.parse_args()
    asyncio.run(main())
