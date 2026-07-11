from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DataIngestionRun, DataRawObject, DataRawRecord, DataSourceSystem

logger = logging.getLogger(__name__)


class WatermarkService:
    """Service to derive the last known processed date (watermark) for a given source system."""

    @staticmethod
    async def get_max_collected_at(
        session: AsyncSession, source_system_name: str
    ) -> datetime | None:
        """Get the maximum collected_at date from DataRawObject for a source."""
        stmt = (
            select(func.max(DataRawObject.collected_at))
            .join(
                DataIngestionRun,
                DataIngestionRun.id == DataRawObject.ingestion_run_id,
            )
            .join(
                DataSourceSystem,
                DataSourceSystem.id == DataIngestionRun.source_system_id,
            )
            .where(DataSourceSystem.name == source_system_name)
        )
        max_date = await session.scalar(stmt)
        return max_date

    @staticmethod
    async def get_max_extracted_at(
        session: AsyncSession, source_system_name: str
    ) -> datetime | None:
        """Get the maximum extracted_at date from DataRawRecord for a source."""
        stmt = (
            select(func.max(DataRawRecord.extracted_at))
            .join(
                DataSourceSystem,
                DataSourceSystem.id == DataRawRecord.source_system_id,
            )
            .where(DataSourceSystem.name == source_system_name)
        )
        max_date = await session.scalar(stmt)
        return max_date

    @staticmethod
    async def get_max_json_field_date(
        session: AsyncSession, source_system_name: str, json_path: str
    ) -> str | None:
        """
        Get the maximum string value of a specific JSON field inside raw_content.
        Useful for deriving the latest 'submission_time' or equivalent content date.
        
        Args:
            json_path: e.g., '$.submission_time'
        """
        stmt = (
            select(func.max(func.json_extract(DataRawRecord.raw_content, json_path)))
            .join(
                DataSourceSystem,
                DataSourceSystem.id == DataRawRecord.source_system_id,
            )
            .where(DataSourceSystem.name == source_system_name)
        )
        max_val = await session.scalar(stmt)
        return str(max_val) if max_val else None
