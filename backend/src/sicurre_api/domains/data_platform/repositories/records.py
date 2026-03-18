from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sicurre_api.domains.data_platform.models import (
    DataAnnotation,
    DataDataset,
    DataDatasetItem,
    DataNormalizedMessage,
    DataProcessingRun,
    DataRawObject,
    DataRawRecord,
)
from sicurre_api.domains.data_platform.schemas import (
    AnnotationCreate,
    DatasetCreate,
    NormalizedMessageCreate,
    NormalizedMessageUpdate,
)


class NormalizedMessageNotFoundError(Exception):
    """Raised when a normalized message does not exist."""


class NormalizedMessageDependencyError(Exception):
    """Raised when a related raw record or processing run is missing."""


class DuplicateNormalizedMessageError(Exception):
    """Raised when a normalized message already exists for the same hash."""


class DuplicateDatasetError(Exception):
    """Raised when a dataset version tag already exists."""


class DatasetNotFoundError(Exception):
    """Raised when a dataset does not exist."""


class RawRecordRepository:
    async def list(
        self,
        session: AsyncSession,
        *,
        source_system_id: UUID | None,
        language: str | None,
        is_usable: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[list[DataRawRecord], int]:
        query: Select[tuple[DataRawRecord]] = (
            select(DataRawRecord)
            .join(DataRawObject, DataRawRecord.raw_object_id == DataRawObject.id)
            .join(DataRawObject.ingestion_run)
            .order_by(DataRawRecord.extracted_at.desc())
        )
        count_query = (
            select(func.count())
            .select_from(DataRawRecord)
            .join(DataRawObject, DataRawRecord.raw_object_id == DataRawObject.id)
            .join(DataRawObject.ingestion_run)
        )

        if source_system_id is not None:
            query = query.where(
                DataRawObject.ingestion_run.has(source_system_id=source_system_id)
            )
            count_query = count_query.where(
                DataRawObject.ingestion_run.has(source_system_id=source_system_id)
            )
        if language is not None:
            query = query.where(DataRawRecord.detected_language == language)
            count_query = count_query.where(DataRawRecord.detected_language == language)
        if is_usable is not None:
            query = query.where(DataRawRecord.is_usable == is_usable)
            count_query = count_query.where(DataRawRecord.is_usable == is_usable)

        items_result = await session.execute(query.limit(limit).offset(offset))
        total_result = await session.execute(count_query)
        return list(items_result.scalars().all()), int(total_result.scalar_one())


class NormalizedMessageRepository:
    async def list(
        self,
        session: AsyncSession,
        *,
        label: str | None,
        language: str | None,
        split: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[DataNormalizedMessage], int]:
        query: Select[tuple[DataNormalizedMessage]] = select(
            DataNormalizedMessage
        ).order_by(DataNormalizedMessage.normalized_at.desc())
        count_query = select(func.count()).select_from(DataNormalizedMessage)

        if split is not None:
            query = query.join(
                DataDatasetItem,
                DataDatasetItem.normalized_message_id == DataNormalizedMessage.id,
            ).where(DataDatasetItem.split_name == split)
            count_query = count_query.join(
                DataDatasetItem,
                DataDatasetItem.normalized_message_id == DataNormalizedMessage.id,
            ).where(DataDatasetItem.split_name == split)

        if label is not None:
            query = query.where(DataNormalizedMessage.current_label == label)
            count_query = count_query.where(
                DataNormalizedMessage.current_label == label
            )
        if language is not None:
            query = query.where(DataNormalizedMessage.language == language)
            count_query = count_query.where(DataNormalizedMessage.language == language)

        items_result = await session.execute(query.limit(limit).offset(offset))
        total_result = await session.execute(count_query)
        return list(items_result.scalars().unique().all()), int(
            total_result.scalar_one()
        )

    async def get(
        self, session: AsyncSession, message_id: UUID
    ) -> DataNormalizedMessage | None:
        return await session.get(DataNormalizedMessage, message_id)

    async def create(
        self, session: AsyncSession, payload: NormalizedMessageCreate
    ) -> DataNormalizedMessage:
        raw_record = await session.get(DataRawRecord, payload.raw_record_id)
        processing_run = await session.get(DataProcessingRun, payload.processing_run_id)
        if raw_record is None or processing_run is None:
            raise NormalizedMessageDependencyError()

        normalized_text = payload.normalized_text
        message = DataNormalizedMessage(
            **payload.model_dump(),
            text_sha256=hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
            text_length=len(normalized_text),
            normalized_at=processing_run.started_at,
        )
        session.add(message)

        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise DuplicateNormalizedMessageError() from exc

        await session.refresh(message)
        return message

    async def update(
        self,
        session: AsyncSession,
        message_id: UUID,
        payload: NormalizedMessageUpdate,
    ) -> DataNormalizedMessage:
        message = await session.get(DataNormalizedMessage, message_id)
        if message is None:
            raise NormalizedMessageNotFoundError(message_id)

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(message, field, value)

        await session.commit()
        await session.refresh(message)
        return message

    async def delete(self, session: AsyncSession, message_id: UUID) -> bool:
        message = await session.get(DataNormalizedMessage, message_id)
        if message is None:
            return False

        await session.delete(message)
        await session.commit()
        return True


class AnnotationRepository:
    async def create(
        self, session: AsyncSession, payload: AnnotationCreate
    ) -> DataAnnotation:
        message = await session.get(
            DataNormalizedMessage, payload.normalized_message_id
        )
        if message is None:
            raise NormalizedMessageNotFoundError(str(payload.normalized_message_id))

        annotation = DataAnnotation(**payload.model_dump())
        session.add(annotation)
        await session.commit()
        await session.refresh(annotation)
        return annotation


class DatasetRepository:
    async def list(
        self,
        session: AsyncSession,
        *,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[DataDataset], int]:
        query = select(DataDataset).order_by(DataDataset.created_at.desc())
        count_query = select(func.count()).select_from(DataDataset)

        if status is not None:
            query = query.where(DataDataset.status == status)
            count_query = count_query.where(DataDataset.status == status)

        items_result = await session.execute(query.limit(limit).offset(offset))
        total_result = await session.execute(count_query)
        return list(items_result.scalars().all()), int(total_result.scalar_one())

    async def create(
        self, session: AsyncSession, payload: DatasetCreate
    ) -> DataDataset:
        dataset = DataDataset(**payload.model_dump())
        session.add(dataset)

        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise DuplicateDatasetError(payload.version_tag) from exc

        await session.refresh(dataset)
        return dataset

    async def list_items(
        self, session: AsyncSession, dataset_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[DataDatasetItem], int]:
        dataset = await session.get(DataDataset, dataset_id)
        if dataset is None:
            raise DatasetNotFoundError(dataset_id)

        items_result = await session.execute(
            select(DataDatasetItem)
            .where(DataDatasetItem.dataset_id == dataset_id)
            .order_by(
                DataDatasetItem.row_order.asc().nulls_last(),
                DataDatasetItem.created_at.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        total_result = await session.execute(
            select(func.count())
            .select_from(DataDatasetItem)
            .where(DataDatasetItem.dataset_id == dataset_id)
        )
        return list(items_result.scalars().all()), int(total_result.scalar_one())
