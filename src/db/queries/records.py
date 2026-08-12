from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from data_platform.api.schemas import (
    AnnotationCreate,
    DatasetCreate,
    NormalizedMessageCreate,
    NormalizedMessageUpdate,
)
from db.models import (
    DataAnnotation,
    DataDataset,
    DataDatasetItem,
    DataNormalizedMessage,
    DataProcessingRun,
    DataRawObject,
    DataRawRecord,
    DatasetStatus,
    SplitName,
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


class DatasetBuildEmptyError(Exception):
    """Raised when a dataset build has no eligible annotated messages."""


@dataclass(slots=True)
class DatasetBuildResult:
    dataset: DataDataset
    split_counts: dict[str, int]


DATASET_BUILD_SEED = "sicurre-dataset-build-v1"
DEFAULT_DATASET_SPLITS: tuple[tuple[str, float], ...] = (
    (SplitName.TRAIN.value, 0.8),
    (SplitName.VAL.value, 0.1),
    (SplitName.TEST.value, 0.1),
)
DEFAULT_DATASET_LABELS: tuple[str, ...] = ("phishing", "spam", "legitimate")


def _stable_dataset_rank(text_sha256: str) -> str:
    return hashlib.sha256(
        f"{DATASET_BUILD_SEED}:{text_sha256}".encode()
    ).hexdigest()


def _uuid_text_match(left: object, right: object) -> object:
    """Compare UUID columns safely across SQLite 32-char/36-char storage.

    SQLite has seen both SQLAlchemy UUID hex storage and reconstructed
    hyphenated text in local POC/data-platform DBs. Normalizing both sides
    keeps local exports and split filters stable while remaining valid on
    PostgreSQL via explicit text casts.
    """
    if isinstance(left, UUID):
        left = str(left)
    if isinstance(right, UUID):
        right = str(right)
    left_text = func.lower(func.replace(sa.cast(left, sa.Text()), "-", ""))
    right_text = func.lower(func.replace(sa.cast(right, sa.Text()), "-", ""))
    return left_text == right_text


def _uuid_string_variants(value: object) -> set[str]:
    text = str(value)
    compact = text.replace("-", "").lower()
    if len(compact) == 32:
        hyphenated = (
            f"{compact[0:8]}-{compact[8:12]}-{compact[12:16]}-"
            f"{compact[16:20]}-{compact[20:32]}"
        )
        return {compact, hyphenated}
    return {text}


def _uuid_canonical(value: object) -> str:
    return str(value).replace("-", "").lower()


def _compute_split_counts(
    total: int,
    splits: tuple[tuple[str, float], ...],
) -> dict[str, int]:
    raw_counts = [(split_name, total * ratio) for split_name, ratio in splits]
    counts = {split_name: math.floor(raw_count) for split_name, raw_count in raw_counts}
    remainder = total - sum(counts.values())
    ranked_remainders = sorted(
        raw_counts,
        key=lambda item: (-(item[1] - math.floor(item[1])), item[0]),
    )

    for split_name, _ in ranked_remainders[:remainder]:
        counts[split_name] += 1

    return counts


class RawRecordQueries:
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


class NormalizedMessageQueries:
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
                _uuid_text_match(
                    DataDatasetItem.normalized_message_id,
                    DataNormalizedMessage.id,
                ),
            ).where(DataDatasetItem.split_name == split)
            count_query = count_query.join(
                DataDatasetItem,
                _uuid_text_match(
                    DataDatasetItem.normalized_message_id,
                    DataNormalizedMessage.id,
                ),
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


class AnnotationQueries:
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


class DatasetQueries:
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

    async def build(
        self,
        session: AsyncSession,
        *,
        name: str,
        version_tag: str,
        target_usage: str,
        status: str,
        include_labels: tuple[str, ...] = DEFAULT_DATASET_LABELS,
        splits: tuple[tuple[str, float], ...] = DEFAULT_DATASET_SPLITS,
        sample_weight: float | None = None,
    ) -> DatasetBuildResult:
        annotation_rank = func.row_number().over(
            partition_by=DataAnnotation.normalized_message_id,
            order_by=(
                DataAnnotation.annotated_at.desc(),
                DataAnnotation.created_at.desc(),
                DataAnnotation.id.desc(),
            ),
        )
        latest_annotations = select(
            DataAnnotation.normalized_message_id.label("normalized_message_id"),
            DataAnnotation.label.label("annotation_label"),
            annotation_rank.label("annotation_rank"),
        ).subquery()

        eligible_result = await session.execute(
            select(
                DataNormalizedMessage.id.label("normalized_message_id"),
                DataNormalizedMessage.text_sha256.label("text_sha256"),
                latest_annotations.c.annotation_label.label("annotation_label"),
            )
            .join(
                latest_annotations,
                latest_annotations.c.normalized_message_id
                == DataNormalizedMessage.id,
            )
            .where(latest_annotations.c.annotation_rank == 1)
            .where(latest_annotations.c.annotation_label.in_(include_labels))
        )
        eligible_rows = [dict(row) for row in eligible_result.mappings().all()]
        if not eligible_rows:
            raise DatasetBuildEmptyError()

        rows_by_label: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in eligible_rows:
            rows_by_label[str(row["annotation_label"])].append(row)

        dataset = DataDataset(
            name=name,
            version_tag=version_tag,
            target_usage=target_usage,
            status=status,
            frozen_at=(
                datetime.now(UTC)
                if status == DatasetStatus.FROZEN.value
                else None
            ),
        )
        session.add(dataset)

        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise DuplicateDatasetError(version_tag) from exc

        total_eligible = len(eligible_rows)
        num_labels = len(rows_by_label)
        label_weights: dict[str, float] = {}
        for label, rows in rows_by_label.items():
            if rows:
                label_weights[label] = round(
                    total_eligible / (num_labels * len(rows)), 4
                )

        split_buckets: dict[str, list[tuple[str, UUID, float]]] = {
            split_name: [] for split_name, _ in splits
        }
        for label in sorted(rows_by_label):
            ranked_rows = sorted(
                rows_by_label[label],
                key=lambda row: _stable_dataset_rank(str(row["text_sha256"])),
            )
            weight = (
                sample_weight
                if sample_weight is not None
                else label_weights.get(label, 1.0)
            )
            label_counts = _compute_split_counts(len(ranked_rows), splits)
            start_index = 0
            for split_name, _ in splits:
                end_index = start_index + label_counts[split_name]
                for row in ranked_rows[start_index:end_index]:
                    split_buckets[split_name].append(
                        (
                            _stable_dataset_rank(str(row["text_sha256"])),
                            row["normalized_message_id"],
                            weight,
                        )
                    )
                start_index = end_index

        row_order = 1
        split_counts: dict[str, int] = {}
        dataset_items: list[dict[str, object]] = []
        created_at = datetime.now(UTC)
        for split_name, _ in splits:
            ordered_rows = sorted(split_buckets[split_name], key=lambda item: item[0])
            split_counts[split_name] = len(ordered_rows)
            for _, normalized_message_id, item_weight in ordered_rows:
                dataset_items.append(
                    {
                        "id": uuid4(),
                        "dataset_id": dataset.id,
                        "normalized_message_id": normalized_message_id,
                        "split_name": split_name,
                        "sample_weight": item_weight,
                        "row_order": row_order,
                        "created_at": created_at,
                    }
                )
                row_order += 1

        await session.execute(sa.insert(DataDatasetItem), dataset_items)

        dataset.item_count = sum(split_counts.values())

        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise DuplicateDatasetError(version_tag) from exc

        await session.refresh(dataset)
        return DatasetBuildResult(dataset=dataset, split_counts=split_counts)

    async def get(self, session: AsyncSession, dataset_id: UUID) -> DataDataset:
        dataset = await session.get(DataDataset, dataset_id)
        if dataset is None:
            raise DatasetNotFoundError(dataset_id)
        return dataset

    async def update_publish_result(
        self,
        session: AsyncSession,
        dataset_id: UUID,
        *,
        kaggle_version_id: int,
        published_at: datetime,
        artifact_uri: str | None = None,
        content_checksum: str | None = None,
        schema_version: str | None = None,
    ) -> None:
        values: dict[str, object] = {
            "kaggle_version_id": kaggle_version_id,
            "published_at": published_at,
        }
        if artifact_uri is not None:
            values["artifact_uri"] = artifact_uri
        if content_checksum is not None:
            values["content_checksum"] = content_checksum
        if schema_version is not None:
            values["schema_version"] = schema_version
        result = await session.execute(
            sa.update(DataDataset)
            .where(sa.cast(DataDataset.id, sa.Text()).in_(_uuid_string_variants(dataset_id)))
            .values(**values)
        )
        if result.rowcount == 0:
            await session.rollback()
            raise DatasetNotFoundError(dataset_id)
        await session.commit()

    async def list_items_for_export(
        self,
        session: AsyncSession,
        dataset_id: UUID,
        *,
        split_name: str,
    ) -> list[tuple[str, str]]:
        """Return (normalized_text, label) pairs for the given split."""
        item_result = await session.execute(
            select(DataDatasetItem.normalized_message_id)
            .where(
                sa.cast(DataDatasetItem.dataset_id, sa.Text()).in_(
                    _uuid_string_variants(dataset_id)
                )
            )
            .where(DataDatasetItem.split_name == split_name)
            .order_by(
                DataDatasetItem.row_order.asc().nulls_last(),
                DataDatasetItem.created_at.asc(),
            )
        )
        item_ids = list(item_result.scalars().all())
        if not item_ids:
            return []

        message_variants: list[str] = []
        for item_id in item_ids:
            message_variants.extend(sorted(_uuid_string_variants(item_id)))

        message_rows: dict[str, tuple[str, str]] = {}
        batch_size = 500
        for start in range(0, len(message_variants), batch_size):
            batch = message_variants[start : start + batch_size]
            result = await session.execute(
                select(
                    DataNormalizedMessage.id,
                    DataNormalizedMessage.normalized_text,
                    DataNormalizedMessage.current_label,
                ).where(sa.cast(DataNormalizedMessage.id, sa.Text()).in_(batch))
            )
            for row in result.all():
                message_rows[_uuid_canonical(row[0])] = (str(row[1]), str(row[2]))

        return [
            message_rows[_uuid_canonical(item_id)]
            for item_id in item_ids
            if _uuid_canonical(item_id) in message_rows
        ]

    async def list_items(
        self, session: AsyncSession, dataset_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[DataDatasetItem], int]:
        dataset = await session.get(DataDataset, dataset_id)
        if dataset is None:
            raise DatasetNotFoundError(dataset_id)

        items_result = await session.execute(
            select(DataDatasetItem)
            .where(
                sa.cast(DataDatasetItem.dataset_id, sa.Text()).in_(
                    _uuid_string_variants(dataset_id)
                )
            )
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
            .where(
                sa.cast(DataDatasetItem.dataset_id, sa.Text()).in_(
                    _uuid_string_variants(dataset_id)
                )
            )
        )
        return list(items_result.scalars().all()), int(total_result.scalar_one())
