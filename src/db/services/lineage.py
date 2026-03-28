from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from db.queries import (
    IngestionRunQueries,
    SourceSystemQueries,
)
from data_platform.api.schemas import (
    DataSourceCreate,
    IngestionRunCreate,
)


class SourceSystemService:
    def __init__(self, repository: SourceSystemQueries | None = None) -> None:
        self.repository = repository or SourceSystemQueries()

    async def list(self, session: AsyncSession, **filters):
        return await self.repository.list(session, **filters)

    async def create(self, session: AsyncSession, payload: DataSourceCreate):
        return await self.repository.create(session, payload)


class IngestionRunService:
    def __init__(self, repository: IngestionRunQueries | None = None) -> None:
        self.repository = repository or IngestionRunQueries()

    async def list(self, session: AsyncSession, **filters):
        return await self.repository.list(session, **filters)

    async def create(self, session: AsyncSession, payload: IngestionRunCreate):
        return await self.repository.create(session, payload)
