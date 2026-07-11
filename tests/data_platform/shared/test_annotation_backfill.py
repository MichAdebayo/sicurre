from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base
from db.models import (
    AnnotationLabelSource,
    DataAnnotation,
    DataIngestionRun,
    DataNormalizedMessage,
    DataProcessingRun,
    DataRawObject,
    DataRawRecord,
    DataSourceSystem,
)
from data_platform.services.shared.annotation_backfill import AnnotationBackfillService


def utc_timestamp() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_annotation_backfill_creates_missing_annotations_for_direct_sources(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        source = DataSourceSystem(name="database-historical", source_type="sql")
        session.add(source)
        await session.flush()

        ingestion = DataIngestionRun(
            source_system_id=source.id,
            started_at=utc_timestamp(),
            status="completed",
            trigger_mode="manual",
        )
        session.add(ingestion)
        await session.flush()

        raw_object = DataRawObject(
            ingestion_run_id=ingestion.id,
            object_type="sql_export",
            content_hash="direct-hash",
            source_metadata={},
            collected_at=utc_timestamp(),
        )
        session.add(raw_object)
        await session.flush()

        raw_record = DataRawRecord(
            raw_object_id=raw_object.id,
            source_system_id=source.id,
            record_key="direct-row-1",
            raw_content="Bonjour",
            detected_language="fr",
            is_usable=True,
            extracted_at=utc_timestamp(),
        )
        session.add(raw_record)
        await session.flush()

        processing_run = DataProcessingRun(
            pipeline_version="direct_normalization_v1",
            started_at=utc_timestamp(),
            finished_at=utc_timestamp(),
            status="completed",
            normalized_count=1,
            rejected_count=0,
        )
        session.add(processing_run)
        await session.flush()

        session.add(
            DataNormalizedMessage(
                raw_record_id=raw_record.id,
                processing_run_id=processing_run.id,
                normalized_text="Objet : Test\n\nBonjour",
                text_sha256="normalized-hash-1",
                language="fr",
                current_label="phishing",
                contains_pii=False,
                redaction_status="not_required",
                text_length=22,
                normalized_at=utc_timestamp(),
            )
        )
        await session.commit()

        result = await AnnotationBackfillService.backfill_missing_annotations(
            session,
            dry_run=False,
        )
        annotations = (await session.execute(select(DataAnnotation))).scalars().all()

    assert result["annotation_count"] == 1
    assert len(annotations) == 1
    assert annotations[0].label == "phishing"
    assert (
        annotations[0].label_source
        == AnnotationLabelSource.NORMALIZED_MESSAGE_BACKFILL.value
    )


@pytest.mark.asyncio
async def test_annotation_backfill_skips_messages_that_already_have_annotations(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        source = DataSourceSystem(
            name="synthetic-generated-certfr-signal-synthetic-certfr-phishing-signal",
            source_type="manual",
        )
        session.add(source)
        await session.flush()

        ingestion = DataIngestionRun(
            source_system_id=source.id,
            started_at=utc_timestamp(),
            status="completed",
            trigger_mode="promotion",
        )
        session.add(ingestion)
        await session.flush()

        raw_object = DataRawObject(
            ingestion_run_id=ingestion.id,
            object_type="api_payload",
            content_hash="generated-hash",
            source_metadata={},
            collected_at=utc_timestamp(),
        )
        session.add(raw_object)
        await session.flush()

        raw_record = DataRawRecord(
            raw_object_id=raw_object.id,
            source_system_id=source.id,
            record_key="generated-row-1",
            raw_content="Bonjour",
            detected_language="fr",
            is_usable=True,
            extracted_at=utc_timestamp(),
        )
        session.add(raw_record)
        await session.flush()

        processing_run = DataProcessingRun(
            pipeline_version="generation_gated_promotion_v1",
            started_at=utc_timestamp(),
            finished_at=utc_timestamp(),
            status="completed",
            normalized_count=1,
            rejected_count=0,
        )
        session.add(processing_run)
        await session.flush()

        message = DataNormalizedMessage(
            raw_record_id=raw_record.id,
            processing_run_id=processing_run.id,
            normalized_text="Objet : Test\n\nBonjour",
            text_sha256="normalized-hash-2",
            language="fr",
            current_label="phishing",
            contains_pii=False,
            redaction_status="not_required",
            text_length=22,
            normalized_at=utc_timestamp(),
        )
        session.add(message)
        await session.flush()

        session.add(
            DataAnnotation(
                normalized_message_id=message.id,
                label="phishing",
                label_source=AnnotationLabelSource.GENERATION_GATED_PROMOTION.value,
                confidence=1.0,
                comment="Existing annotation.",
                is_validated=False,
                annotated_at=utc_timestamp(),
            )
        )
        await session.commit()

        result = await AnnotationBackfillService.backfill_missing_annotations(
            session,
            dry_run=False,
        )
        annotations = (await session.execute(select(DataAnnotation))).scalars().all()

    assert result["annotation_count"] == 0
    assert len(annotations) == 1


@pytest.mark.asyncio
async def test_annotation_backfill_database_parent_filter_matches_child_sources(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        source = DataSourceSystem(
            name="database/adapted/adapted_en_fr",
            source_type="sql",
        )
        session.add(source)
        await session.flush()

        ingestion = DataIngestionRun(
            source_system_id=source.id,
            started_at=utc_timestamp(),
            status="completed",
            trigger_mode="manual",
        )
        session.add(ingestion)
        await session.flush()

        raw_object = DataRawObject(
            ingestion_run_id=ingestion.id,
            object_type="sql_export",
            content_hash="database-child-hash",
            source_metadata={},
            collected_at=utc_timestamp(),
        )
        session.add(raw_object)
        await session.flush()

        raw_record = DataRawRecord(
            raw_object_id=raw_object.id,
            source_system_id=source.id,
            record_key="database-child-row-1",
            raw_content="Bonjour",
            detected_language="fr",
            is_usable=True,
            extracted_at=utc_timestamp(),
        )
        session.add(raw_record)
        await session.flush()

        processing_run = DataProcessingRun(
            pipeline_version="direct_normalization_v1",
            started_at=utc_timestamp(),
            finished_at=utc_timestamp(),
            status="completed",
            normalized_count=1,
            rejected_count=0,
        )
        session.add(processing_run)
        await session.flush()

        session.add(
            DataNormalizedMessage(
                raw_record_id=raw_record.id,
                processing_run_id=processing_run.id,
                normalized_text="Objet : Test\n\nBonjour",
                text_sha256="normalized-hash-database-child",
                language="fr",
                current_label="phishing",
                contains_pii=False,
                redaction_status="not_required",
                text_length=22,
                normalized_at=utc_timestamp(),
            )
        )
        await session.commit()

        result = await AnnotationBackfillService.backfill_missing_annotations(
            session,
            source_names=("database-historical",),
            dry_run=False,
        )
        annotations = (await session.execute(select(DataAnnotation))).scalars().all()

    assert result["annotation_count"] == 1
    assert len(annotations) == 1
    assert annotations[0].label == "phishing"
    assert (
        annotations[0].label_source
        == AnnotationLabelSource.NORMALIZED_MESSAGE_BACKFILL.value
    )
