from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import aliased

from core.config import get_settings
from db.models import (
    DataIngestionRun,
    DataNormalizedMessage,
    DataProcessingRun,
    DataRawObject,
    DataRawRecord,
    DataSourceSystem,
)


SOURCE_NAME = "common-crawl-bigdata"


async def _collect_counts(session: AsyncSession, source_id) -> dict[str, int]:
    raw_objects = await session.scalar(
        select(func.count(DataRawObject.id))
        .join(DataIngestionRun, DataRawObject.ingestion_run_id == DataIngestionRun.id)
        .where(DataIngestionRun.source_system_id == source_id)
    )
    raw_records = await session.scalar(
        select(func.count(DataRawRecord.id))
        .join(DataRawObject, DataRawRecord.raw_object_id == DataRawObject.id)
        .join(DataIngestionRun, DataRawObject.ingestion_run_id == DataIngestionRun.id)
        .where(DataIngestionRun.source_system_id == source_id)
    )
    direct_raw_records = await session.scalar(
        select(func.count(DataRawRecord.id)).where(
            DataRawRecord.source_system_id == source_id
        )
    )
    raw_object_alias = aliased(DataRawObject)
    orphan_raw_records = await session.scalar(
        select(func.count(DataRawRecord.id))
        .select_from(DataRawRecord)
        .outerjoin(raw_object_alias, DataRawRecord.raw_object_id == raw_object_alias.id)
        .where(
            DataRawRecord.source_system_id == source_id,
            raw_object_alias.id.is_(None),
        )
    )
    normalized_messages = await session.scalar(
        select(func.count(DataNormalizedMessage.id))
        .join(DataRawRecord, DataNormalizedMessage.raw_record_id == DataRawRecord.id)
        .join(DataRawObject, DataRawRecord.raw_object_id == DataRawObject.id)
        .join(DataIngestionRun, DataRawObject.ingestion_run_id == DataIngestionRun.id)
        .where(DataIngestionRun.source_system_id == source_id)
    )
    processing_runs = await session.scalar(
        select(func.count(func.distinct(DataProcessingRun.id)))
        .join(
            DataNormalizedMessage,
            DataNormalizedMessage.processing_run_id == DataProcessingRun.id,
        )
        .join(DataRawRecord, DataNormalizedMessage.raw_record_id == DataRawRecord.id)
        .join(DataRawObject, DataRawRecord.raw_object_id == DataRawObject.id)
        .join(DataIngestionRun, DataRawObject.ingestion_run_id == DataIngestionRun.id)
        .where(DataIngestionRun.source_system_id == source_id)
    )
    ingestion_runs = await session.scalar(
        select(func.count(DataIngestionRun.id)).where(
            DataIngestionRun.source_system_id == source_id
        )
    )
    return {
        "ingestion_runs": ingestion_runs or 0,
        "raw_objects": raw_objects or 0,
        "raw_records": raw_records or 0,
        "raw_records_direct": direct_raw_records or 0,
        "orphan_raw_records": orphan_raw_records or 0,
        "normalized_messages": normalized_messages or 0,
        "processing_runs_touching_source": processing_runs or 0,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete Common Crawl ingestion runs and cascading raw lineage after confirming there are no normalized-message dependencies."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply the deletion. Without this flag the script only reports what would be removed.",
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    async with session_factory() as session:
        source = await session.scalar(
            select(DataSourceSystem).where(DataSourceSystem.name == SOURCE_NAME)
        )
        if source is None:
            payload = {
                "database_url": settings.database_url,
                "source_name": SOURCE_NAME,
                "source_exists": False,
                "deleted": False,
            }
            json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
            await engine.dispose()
            return

        before_counts = await _collect_counts(session, source.id)
        blocked = (
            before_counts["normalized_messages"] > 0
            or before_counts["processing_runs_touching_source"] > 0
        )
        payload = {
            "database_url": settings.database_url,
            "source_name": SOURCE_NAME,
            "source_exists": True,
            "source_id": str(source.id),
            "execute": args.execute,
            "before_counts": before_counts,
            "deleted": False,
        }

        if blocked:
            payload["blocked_reason"] = (
                "Common Crawl source still has normalized-message dependencies; refusing to delete raw lineage."
            )
            json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
            await engine.dispose()
            return

        if not args.execute:
            payload["would_delete"] = {
                "ingestion_runs": before_counts["ingestion_runs"],
                "raw_objects": before_counts["raw_objects"],
                "raw_records": before_counts["raw_records"],
            }
            json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
            await engine.dispose()
            return

        await session.execute(
            delete(DataRawRecord).where(DataRawRecord.source_system_id == source.id)
        )
        ingestion_run_ids = select(DataIngestionRun.id).where(
            DataIngestionRun.source_system_id == source.id
        )
        await session.execute(
            delete(DataRawObject).where(
                DataRawObject.ingestion_run_id.in_(ingestion_run_ids)
            )
        )
        await session.execute(
            delete(DataIngestionRun).where(
                DataIngestionRun.source_system_id == source.id
            )
        )
        await session.commit()

        after_counts = await _collect_counts(session, source.id)
        payload["deleted"] = True
        payload["after_counts"] = after_counts

    await engine.dispose()
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    asyncio.run(main())
