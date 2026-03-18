from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from sicurre_api.domains.data_platform.repositories import (
    AnnotationRepository,
    DatasetRepository,
    NormalizedMessageRepository,
    RawRecordRepository,
)
from sicurre_api.domains.data_platform.schemas import (
    AnnotationCreate,
    DatasetCreate,
    NormalizedMessageCreate,
    NormalizedMessageUpdate,
)
from sicurre_api.domains.data_platform.services.normalization import (
    TextNormalizationService,
)


class RawRecordService:
    def __init__(self, repository: RawRecordRepository | None = None) -> None:
        self.repository = repository or RawRecordRepository()

    async def list(self, session: AsyncSession, **filters):
        return await self.repository.list(session, **filters)


class NormalizedMessageService:
    def __init__(
        self,
        repository: NormalizedMessageRepository | None = None,
        normalization_service: TextNormalizationService | None = None,
    ) -> None:
        self.repository = repository or NormalizedMessageRepository()
        self.normalization_service = normalization_service or TextNormalizationService()

    async def list(self, session: AsyncSession, **filters):
        return await self.repository.list(session, **filters)

    async def get(self, session: AsyncSession, message_id: UUID):
        return await self.repository.get(session, message_id)

    async def create(self, session: AsyncSession, payload: NormalizedMessageCreate):
        artifact = self.normalization_service.normalize_text(payload.normalized_text)
        normalized_payload = payload.model_copy(
            update={
                "normalized_text": artifact.cleaned_text,
                "contains_pii": payload.contains_pii
                or artifact.contains_redaction_tokens,
            }
        )
        return await self.repository.create(session, normalized_payload)

    async def update(
        self, session: AsyncSession, message_id: UUID, payload: NormalizedMessageUpdate
    ):
        return await self.repository.update(session, message_id, payload)

    async def delete(self, session: AsyncSession, message_id: UUID) -> bool:
        return await self.repository.delete(session, message_id)


class AnnotationService:
    def __init__(self, repository: AnnotationRepository | None = None) -> None:
        self.repository = repository or AnnotationRepository()

    async def create(self, session: AsyncSession, payload: AnnotationCreate):
        return await self.repository.create(session, payload)


class DatasetService:
    def __init__(self, repository: DatasetRepository | None = None) -> None:
        self.repository = repository or DatasetRepository()

    async def list(self, session: AsyncSession, **filters):
        return await self.repository.list(session, **filters)

    async def create(self, session: AsyncSession, payload: DatasetCreate):
        return await self.repository.create(session, payload)

    async def list_items(self, session: AsyncSession, dataset_id: UUID, **filters):
        return await self.repository.list_items(session, dataset_id, **filters)
