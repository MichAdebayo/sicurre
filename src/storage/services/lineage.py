from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from storage.repositories import (
    IngestionRunRepository,
    SourceSystemRepository,
)
from data_platform.api.schemas import (
    DataSourceCreate,
    IngestionRunCreate,
)


class SourceSystemService:
    def __init__(self, repository: SourceSystemRepository | None = None) -> None:
        self.repository = repository or SourceSystemRepository()

    async def list(self, session: AsyncSession, **filters):
        return await self.repository.list(session, **filters)

    async def create(self, session: AsyncSession, payload: DataSourceCreate):
        return await self.repository.create(session, payload)


class IngestionRunService:
    def __init__(self, repository: IngestionRunRepository | None = None) -> None:
        self.repository = repository or IngestionRunRepository()

    async def list(self, session: AsyncSession, **filters):
        return await self.repository.list(session, **filters)

    async def create(self, session: AsyncSession, payload: IngestionRunCreate):
        return await self.repository.create(session, payload)
