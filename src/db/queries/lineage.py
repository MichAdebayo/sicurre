from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DataIngestionRun, DataSourceSystem
from data_platform.api.schemas import (
    DataSourceCreate,
    IngestionRunCreate,
)


class DuplicateDataSourceError(Exception):
    """Raised when a source system name already exists."""


class SourceSystemNotFoundError(Exception):
    """Raised when an ingestion run references a missing source system."""


class SourceSystemQueries:
    async def get_by_name(
        self, session: AsyncSession, name: str
    ) -> DataSourceSystem | None:
        result = await session.execute(
            select(DataSourceSystem).where(DataSourceSystem.name == name)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        session: AsyncSession,
        *,
        source_type: str | None,
        is_active: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[list[DataSourceSystem], int]:
        query = select(DataSourceSystem).order_by(DataSourceSystem.created_at.desc())
        count_query = select(func.count()).select_from(DataSourceSystem)

        if source_type is not None:
            query = query.where(DataSourceSystem.source_type == source_type)
            count_query = count_query.where(DataSourceSystem.source_type == source_type)
        if is_active is not None:
            query = query.where(DataSourceSystem.is_active == is_active)
            count_query = count_query.where(DataSourceSystem.is_active == is_active)

        items_result = await session.execute(query.limit(limit).offset(offset))
        total_result = await session.execute(count_query)
        return list(items_result.scalars().all()), int(total_result.scalar_one())

    async def create(
        self, session: AsyncSession, payload: DataSourceCreate
    ) -> DataSourceSystem:
        source_system = DataSourceSystem(**payload.model_dump())
        session.add(source_system)

        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise DuplicateDataSourceError(payload.name) from exc

        await session.refresh(source_system)
        return source_system


class IngestionRunQueries:
    async def list(
        self,
        session: AsyncSession,
        *,
        source_system_id: UUID | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[DataIngestionRun], int]:
        query = select(DataIngestionRun).order_by(DataIngestionRun.started_at.desc())
        count_query = select(func.count()).select_from(DataIngestionRun)

        if source_system_id is not None:
            query = query.where(DataIngestionRun.source_system_id == source_system_id)
            count_query = count_query.where(
                DataIngestionRun.source_system_id == source_system_id
            )
        if status is not None:
            query = query.where(DataIngestionRun.status == status)
            count_query = count_query.where(DataIngestionRun.status == status)

        items_result = await session.execute(query.limit(limit).offset(offset))
        total_result = await session.execute(count_query)
        return list(items_result.scalars().all()), int(total_result.scalar_one())

    async def create(
        self, session: AsyncSession, payload: IngestionRunCreate
    ) -> DataIngestionRun:
        source_system = await session.get(DataSourceSystem, payload.source_system_id)
        if source_system is None:
            raise SourceSystemNotFoundError(str(payload.source_system_id))

        ingestion_run = DataIngestionRun(**payload.model_dump())
        session.add(ingestion_run)
        await session.commit()
        await session.refresh(ingestion_run)
        return ingestion_run
