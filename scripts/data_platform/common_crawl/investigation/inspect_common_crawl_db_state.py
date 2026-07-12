from __future__ import annotations

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

from sqlalchemy import func, select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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


async def _scalar(session: AsyncSession, statement):
    return await session.scalar(statement)


async def main() -> None:
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
            }
            json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
            await engine.dispose()
            return

        raw_record_join = (
            select(func.count(DataRawRecord.id))
            .join(DataRawObject, DataRawRecord.raw_object_id == DataRawObject.id)
            .join(
                DataIngestionRun,
                DataRawObject.ingestion_run_id == DataIngestionRun.id,
            )
            .where(DataIngestionRun.source_system_id == source.id)
        )
        direct_raw_record_count = select(func.count(DataRawRecord.id)).where(
            DataRawRecord.source_system_id == source.id
        )
        raw_object_alias = aliased(DataRawObject)
        orphan_raw_records = (
            select(func.count(DataRawRecord.id))
            .select_from(DataRawRecord)
            .outerjoin(
                raw_object_alias, DataRawRecord.raw_object_id == raw_object_alias.id
            )
            .where(
                DataRawRecord.source_system_id == source.id,
                raw_object_alias.id.is_(None),
            )
        )
        normalized_join = (
            select(func.count(DataNormalizedMessage.id))
            .join(
                DataRawRecord, DataNormalizedMessage.raw_record_id == DataRawRecord.id
            )
            .join(DataRawObject, DataRawRecord.raw_object_id == DataRawObject.id)
            .join(
                DataIngestionRun,
                DataRawObject.ingestion_run_id == DataIngestionRun.id,
            )
            .where(DataIngestionRun.source_system_id == source.id)
        )
        processing_join = (
            select(func.count(func.distinct(DataProcessingRun.id)))
            .join(
                DataNormalizedMessage,
                DataNormalizedMessage.processing_run_id == DataProcessingRun.id,
            )
            .join(
                DataRawRecord, DataNormalizedMessage.raw_record_id == DataRawRecord.id
            )
            .join(DataRawObject, DataRawRecord.raw_object_id == DataRawObject.id)
            .join(
                DataIngestionRun,
                DataRawObject.ingestion_run_id == DataIngestionRun.id,
            )
            .where(DataIngestionRun.source_system_id == source.id)
        )

        latest_runs_result = await session.execute(
            select(DataIngestionRun)
            .where(DataIngestionRun.source_system_id == source.id)
            .order_by(DataIngestionRun.started_at.desc())
            .limit(10)
        )
        latest_runs = latest_runs_result.scalars().all()

        payload = {
            "database_url": settings.database_url,
            "source_name": SOURCE_NAME,
            "source_exists": True,
            "source_id": str(source.id),
            "counts": {
                "ingestion_runs": await _scalar(
                    session,
                    select(func.count(DataIngestionRun.id)).where(
                        DataIngestionRun.source_system_id == source.id
                    ),
                ),
                "raw_objects": await _scalar(
                    session,
                    select(func.count(DataRawObject.id))
                    .join(
                        DataIngestionRun,
                        DataRawObject.ingestion_run_id == DataIngestionRun.id,
                    )
                    .where(DataIngestionRun.source_system_id == source.id),
                ),
                "raw_records": await _scalar(session, raw_record_join),
                "raw_records_direct": await _scalar(session, direct_raw_record_count),
                "orphan_raw_records": await _scalar(session, orphan_raw_records),
                "normalized_messages": await _scalar(session, normalized_join),
                "processing_runs_touching_source": await _scalar(
                    session, processing_join
                ),
            },
            "latest_ingestion_runs": [
                {
                    "id": str(run.id),
                    "started_at": run.started_at.isoformat(),
                    "finished_at": (
                        run.finished_at.isoformat() if run.finished_at else None
                    ),
                    "status": run.status,
                    "trigger_mode": run.trigger_mode,
                    "raw_object_count": run.raw_object_count,
                    "raw_record_count": run.raw_record_count,
                    "log_message": run.log_message,
                }
                for run in latest_runs
            ],
        }

    await engine.dispose()
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    asyncio.run(main())
