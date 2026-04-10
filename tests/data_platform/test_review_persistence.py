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
    DataAnnotation,
    DataGenerationRun,
    DataGenerationSample,
    DataIngestionRun,
    DataNormalizedMessage,
    DataProcessingRun,
    DataRawObject,
    DataRawRecord,
    DataSourceSystem,
)
from data_platform.services.review_persistence import ReviewPersistenceService


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


@pytest_asyncio.fixture
async def seeded_raw_records(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, str]:
    async with session_factory() as session:
        source = DataSourceSystem(name="seed-source", source_type="file")
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
            object_type="file",
            content_hash="seed-hash",
            source_metadata={},
            collected_at=utc_timestamp(),
        )
        session.add(raw_object)
        await session.flush()

        raw_record_one = DataRawRecord(
            raw_object_id=raw_object.id,
            record_key="row-1",
            raw_content="Bonjour",
            detected_language="fr",
            is_usable=True,
            extracted_at=utc_timestamp(),
        )
        raw_record_two = DataRawRecord(
            raw_object_id=raw_object.id,
            record_key="row-2",
            raw_content="Salut",
            detected_language="fr",
            is_usable=True,
            extracted_at=utc_timestamp(),
        )
        session.add_all([raw_record_one, raw_record_two])
        await session.commit()

        return {
            "raw_record_one": str(raw_record_one.id),
            "raw_record_two": str(raw_record_two.id),
        }


@pytest.mark.asyncio
async def test_persist_generation_bundle_creates_run_and_samples(
    session_factory: async_sessionmaker[AsyncSession],
    seeded_raw_records: dict[str, str],
) -> None:
    payload = {
        "run": {
            "generator_name": "common_crawl_signal_synthetic",
            "source_name": "common-crawl-phishing-signal",
            "parent_source": "common-crawl-bigdata",
            "reference_selection_mode": "reviewed_export_phishing_seed",
            "input_artifact_uri": "tasks/input.json",
            "generated_artifact_uri": "tasks/generated.json",
            "status": "completed",
            "total_draft_count": 1,
            "usable_draft_count": 1,
            "needs_prompt_tuning_count": 0,
            "dropped_draft_count": 0,
            "created_at": utc_timestamp().isoformat(),
        },
        "samples": [
            {
                "draft_id": "draft-1",
                "scenario_id": "delivery:test",
                "variant_index": 0,
                "source_name": "common-crawl-phishing-signal",
                "parent_source": "common-crawl-bigdata",
                "target_label": "phishing",
                "primary_theme": "delivery",
                "review_state": "usable",
                "review_notes": [],
                "text_sha256": "abc123",
                "nearest_reference_raw_record_id": seeded_raw_records["raw_record_one"],
                "nearest_similarity": 1.0,
            }
        ],
    }

    async with session_factory() as session:
        result = await ReviewPersistenceService.persist_generation_bundle(
            session,
            payload,
        )
        runs = (await session.execute(select(DataGenerationRun))).scalars().all()
        samples = (await session.execute(select(DataGenerationSample))).scalars().all()

    assert result["sample_count"] == 1
    assert len(runs) == 1
    assert len(samples) == 1
    assert samples[0].draft_id == "draft-1"
    assert (
        str(samples[0].nearest_reference_raw_record_id)
        == seeded_raw_records["raw_record_one"]
    )


@pytest.mark.asyncio
async def test_persist_common_crawl_acceptance_review_creates_messages_and_annotations(
    session_factory: async_sessionmaker[AsyncSession],
    seeded_raw_records: dict[str, str],
) -> None:
    payload = {
        "accepted_candidates": [
            {
                "candidate_id": "candidate-1",
                "raw_record_id": seeded_raw_records["raw_record_two"],
                "target_label": "spam",
            }
        ],
        "rejected_candidate_count": 2,
        "proposed_normalized_messages": [
            {
                "raw_record_id": seeded_raw_records["raw_record_two"],
                "normalized_text": "Objet : Offre prioritaire\n\nBonjour,\n\nMessage revu.",
                "text_sha256": "hash-acceptance-1",
                "language": "fr",
                "current_label": "spam",
                "contains_pii": False,
                "redaction_status": "not_required",
                "text_length": 50,
                "lineage_candidate_id": "candidate-1",
            }
        ],
        "proposed_annotations": [
            {
                "candidate_id": "candidate-1",
                "raw_record_id": seeded_raw_records["raw_record_two"],
                "label": "spam",
                "label_source": "common_crawl_acceptance_review",
                "confidence": 0.8,
                "comment": "Pending curated promotion.",
                "is_validated": False,
            }
        ],
    }

    async with session_factory() as session:
        result = await ReviewPersistenceService.persist_common_crawl_acceptance_review(
            session,
            payload,
            pipeline_version="common_crawl_reviewed_promotion_v1",
            report_uri="tasks/review.json",
        )
        processing_runs = (
            (await session.execute(select(DataProcessingRun))).scalars().all()
        )
        messages = (
            (await session.execute(select(DataNormalizedMessage))).scalars().all()
        )
        annotations = (await session.execute(select(DataAnnotation))).scalars().all()

    assert result["normalized_message_count"] == 1
    assert result["annotation_count"] == 1
    assert len(processing_runs) == 1
    assert processing_runs[0].normalized_count == 1
    assert processing_runs[0].rejected_count == 2
    assert len(messages) == 1
    assert messages[0].current_label == "spam"
    assert len(annotations) == 1
    assert annotations[0].label_source == "common_crawl_acceptance_review"
