from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base
from data_platform.services.shared.review_persistence import ReviewPersistenceService
from db.models import (
    AnnotationLabelSource,
    DataAnnotation,
    DataGenerationRun,
    DataGenerationSample,
    DataGenerationSampleSourceLink,
    DataIngestionRun,
    DataNormalizedMessage,
    DataProcessingRun,
    DataRawObject,
    DataRawRecord,
    DataSourceSystem,
    GenerationSourceLinkRole,
)


def utc_timestamp() -> datetime:
    return datetime.now(UTC)


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
        raw_record_three = DataRawRecord(
            raw_object_id=raw_object.id,
            record_key="row-3",
            raw_content="Bonsoir",
            detected_language="fr",
            is_usable=True,
            extracted_at=utc_timestamp(),
        )
        session.add_all([raw_record_one, raw_record_two, raw_record_three])
        await session.commit()

        return {
            "raw_record_one": str(raw_record_one.id),
            "raw_record_two": str(raw_record_two.id),
            "raw_record_three": str(raw_record_three.id),
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
async def test_persist_generation_bundle_persists_source_links(
    session_factory: async_sessionmaker[AsyncSession],
    seeded_raw_records: dict[str, str],
) -> None:
    payload = {
        "run": {
            "generator_name": "adapted_phishing_generator",
            "source_name": "adapted_en_fr",
            "parent_source": "zefang_phishing",
            "status": "completed",
            "created_at": utc_timestamp().isoformat(),
        },
        "samples": [
            {
                "draft_id": "draft-linked",
                "variant_index": 0,
                "source_name": "adapted_en_fr",
                "parent_source": "zefang_phishing",
                "target_label": "phishing",
                "review_state": "usable",
                "review_notes": [],
                "text_sha256": "linked-hash-1",
                "source_raw_record_id": seeded_raw_records["raw_record_one"],
                "sampled_record_ids": [seeded_raw_records["raw_record_two"]],
                "nearest_reference_raw_record_id": seeded_raw_records[
                    "raw_record_three"
                ],
                "nearest_similarity": 0.93,
            }
        ],
    }

    async with session_factory() as session:
        await ReviewPersistenceService.persist_generation_bundle(session, payload)
        source_links = (
            (
                await session.execute(
                    select(DataGenerationSampleSourceLink).order_by(
                        DataGenerationSampleSourceLink.link_order
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(source_links) == 3
    assert [link.link_role for link in source_links] == [
        GenerationSourceLinkRole.GENERATION_SEED.value,
        GenerationSourceLinkRole.SAMPLE_INPUT.value,
        GenerationSourceLinkRole.NEAREST_REFERENCE.value,
    ]
    assert [str(link.raw_record_id) for link in source_links] == [
        seeded_raw_records["raw_record_one"],
        seeded_raw_records["raw_record_two"],
        seeded_raw_records["raw_record_three"],
    ]


@pytest.mark.asyncio
async def test_persist_generation_bundle_allows_archetype_only_samples_without_source_links(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "run": {
            "generator_name": "synthetic_archetype_generator",
            "source_name": "synthetic_phishing",
            "status": "completed",
            "created_at": utc_timestamp().isoformat(),
        },
        "samples": [
            {
                "draft_id": "draft-archetype-only",
                "variant_index": 0,
                "source_name": "synthetic_phishing",
                "target_label": "phishing",
                "review_state": "usable",
                "review_notes": [],
                "text_sha256": "archetype-hash-1",
                "en_source_raw_record_id": "template_only",
            }
        ],
    }

    async with session_factory() as session:
        await ReviewPersistenceService.persist_generation_bundle(session, payload)
        source_links = (
            (await session.execute(select(DataGenerationSampleSourceLink)))
            .scalars()
            .all()
        )

    assert source_links == []


@pytest.mark.asyncio
async def test_persist_common_crawl_reviewed_export_builds_acceptance_and_persists(
    session_factory: async_sessionmaker[AsyncSession],
    seeded_raw_records: dict[str, str],
) -> None:
    payload = {
        "mode": "stage_two_reviewed_export",
        "candidates": [
            {
                "candidate_id": "candidate-accepted",
                "draft_id": "draft-accepted",
                "raw_record_id": seeded_raw_records["raw_record_one"],
                "source_name": "common-crawl-bigdata",
                "rule_key": "instructional_legitimate",
                "rewrite_mode": "rewrite",
                "target_label": "legitimate",
                "review_state": "usable",
                "review_notes": [],
                "quality_signals": {
                    "french_marker_count": 5,
                    "target_cue_hits": 1,
                },
                "normalized_text": (
                    "Objet : Mise a jour de votre espace client\n\n"
                    "Bonjour,\n\n"
                    "Nous confirmons que votre dossier administratif reste accessible "
                    "depuis votre espace client. Merci de relire les informations de "
                    "contact et de telecharger l'attestation jointe avant le 18 avril "
                    "afin d'eviter toute interruption de service.\n\n"
                    "Cordialement,\nLe service clients"
                ),
                "text_length": 288,
                "text_sha256": "reviewed-export-hash-1",
                "contains_pii": False,
                "redaction_status": "not_required",
            },
            {
                "candidate_id": "candidate-rejected",
                "draft_id": "draft-rejected",
                "raw_record_id": seeded_raw_records["raw_record_two"],
                "source_name": "common-crawl-bigdata",
                "rule_key": "instructional_legitimate",
                "rewrite_mode": "rewrite",
                "target_label": "legitimate",
                "review_state": "needs_prompt_tuning",
                "review_notes": [],
                "quality_signals": {
                    "french_marker_count": 5,
                    "target_cue_hits": 1,
                },
                "normalized_text": (
                    "Objet : Dossier incomplet\n\n"
                    "Bonjour,\n\n"
                    "Ce texte resterait assez long pour passer les filtres de longueur, "
                    "mais son etat de revue doit empecher toute promotion directe.\n\n"
                    "Cordialement"
                ),
                "text_length": 220,
                "text_sha256": "reviewed-export-hash-2",
                "contains_pii": False,
                "redaction_status": "not_required",
            },
        ],
    }

    async with session_factory() as session:
        result = await ReviewPersistenceService.persist_common_crawl_reviewed_export(
            session,
            payload,
            pipeline_version="common_crawl_reviewed_promotion_v1",
            report_uri="tasks/reviewed-export.json",
        )
        processing_runs = (
            (await session.execute(select(DataProcessingRun))).scalars().all()
        )
        messages = (
            (await session.execute(select(DataNormalizedMessage))).scalars().all()
        )
        annotations = (await session.execute(select(DataAnnotation))).scalars().all()

    assert result["reviewed_candidate_count"] == 2
    assert result["accepted_candidate_count"] == 1
    assert result["rejected_candidate_count"] == 1
    assert result["normalized_message_count"] == 1
    assert result["annotation_count"] == 1
    assert len(processing_runs) == 1
    assert processing_runs[0].normalized_count == 1
    assert processing_runs[0].rejected_count == 1
    assert processing_runs[0].report_uri == "tasks/reviewed-export.json"
    assert len(messages) == 1
    assert messages[0].current_label == "legitimate"
    assert str(messages[0].raw_record_id) == seeded_raw_records["raw_record_one"]
    assert len(annotations) == 1
    assert (
        annotations[0].label_source
        == AnnotationLabelSource.COMMON_CRAWL_ACCEPTANCE_REVIEW.value
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
    assert (
        annotations[0].label_source
        == AnnotationLabelSource.COMMON_CRAWL_ACCEPTANCE_REVIEW.value
    )


@pytest.mark.asyncio
async def test_persist_common_crawl_reviewed_export_rejects_missing_raw_record_ids(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "mode": "stage_two_reviewed_export",
        "candidates": [
            {
                "candidate_id": "candidate-missing-raw",
                "draft_id": "draft-missing-raw",
                "raw_record_id": "00000000-0000-0000-0000-000000000001",
                "source_name": "common-crawl-bigdata",
                "rule_key": "instructional_legitimate",
                "rewrite_mode": "rewrite",
                "target_label": "legitimate",
                "review_state": "usable",
                "review_notes": [],
                "quality_signals": {
                    "french_marker_count": 5,
                    "target_cue_hits": 1,
                },
                "normalized_text": (
                    "Objet : Mise a jour de votre espace client\n\n"
                    "Bonjour,\n\n"
                    "Nous confirmons que votre dossier administratif reste accessible "
                    "depuis votre espace client. Merci de relire les informations de "
                    "contact et de telecharger l'attestation jointe avant le 18 avril "
                    "afin d'eviter toute interruption de service.\n\n"
                    "Cordialement,\nLe service clients"
                ),
                "text_length": 288,
                "text_sha256": "reviewed-export-missing-raw",
                "contains_pii": False,
                "redaction_status": "not_required",
            }
        ],
    }

    async with session_factory() as session:
        with pytest.raises(
            ValueError,
            match=r"Common Crawl acceptance review references 1 raw_record_id value\(s\) not present in the current DB",
        ):
            await ReviewPersistenceService.persist_common_crawl_reviewed_export(
                session,
                payload,
                pipeline_version="common_crawl_reviewed_promotion_v1",
                report_uri="tasks/reviewed-export.json",
            )

        processing_runs = (
            (await session.execute(select(DataProcessingRun))).scalars().all()
        )
        messages = (
            (await session.execute(select(DataNormalizedMessage))).scalars().all()
        )
        annotations = (await session.execute(select(DataAnnotation))).scalars().all()

    assert processing_runs == []
    assert messages == []
    assert annotations == []


@pytest.mark.asyncio
async def test_persist_generated_promotion_review_creates_raw_lineage_and_annotations(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "run": {
            "generator_name": "adapted_phishing_generator",
            "source_name": "adapted_en_fr",
            "generated_artifact_uri": "tasks/generated-adapted.json",
        },
        "selected_draft_ids": ["draft-2"],
        "promoted_samples": [
            {
                "draft_id": "draft-1",
                "variant_index": 0,
                "review_state": "usable",
                "target_label": "phishing",
                "normalized_text": (
                    "Objet : Mise a jour\n\nBonjour,\n\n"
                    "Ceci est le brouillon non promu."
                ),
                "text_sha256": "generated-hash-1",
                "language": "fr",
            },
            {
                "draft_id": "draft-2",
                "variant_index": 0,
                "review_state": "usable",
                "target_label": "phishing",
                "normalized_text": "Objet : Verification urgente\n\nBonjour,\n\nMerci de verifier votre compte.",
                "text_sha256": "generated-hash-2",
                "language": "fr",
                "annotation": {
                    "label": "phishing",
                    "label_source": "generated_promotion_review",
                    "confidence": 0.91,
                    "comment": "Eligible for curator review.",
                    "is_validated": False,
                },
            },
        ],
    }

    async with session_factory() as session:
        result = await ReviewPersistenceService.persist_generated_promotion_review(
            session,
            payload,
            pipeline_version="generated_reviewed_promotion_v1",
            report_uri="tasks/generated-review.json",
        )
        source_systems = (
            (await session.execute(select(DataSourceSystem))).scalars().all()
        )
        ingestion_runs = (
            (await session.execute(select(DataIngestionRun))).scalars().all()
        )
        raw_objects = (await session.execute(select(DataRawObject))).scalars().all()
        raw_records = (await session.execute(select(DataRawRecord))).scalars().all()
        processing_runs = (
            (await session.execute(select(DataProcessingRun))).scalars().all()
        )
        messages = (
            (await session.execute(select(DataNormalizedMessage))).scalars().all()
        )
        annotations = (await session.execute(select(DataAnnotation))).scalars().all()

    assert result["raw_record_count"] == 1
    assert result["normalized_message_count"] == 1
    assert result["annotation_count"] == 1
    assert len(source_systems) == 1
    assert source_systems[0].name == (
        "synthetic-generated-adapted-phishing-generator-adapted-en-fr"
    )
    assert source_systems[0].source_type == "manual"
    assert len(ingestion_runs) == 1
    assert ingestion_runs[0].trigger_mode == "promotion"
    assert len(raw_objects) == 1
    assert len(raw_records) == 1
    assert raw_records[0].record_key == "draft-2:0"
    assert raw_records[0].source_system_id == source_systems[0].id
    assert raw_records[0].generation_sample_id is None
    assert len(processing_runs) == 1
    assert len(messages) == 1
    assert messages[0].current_label == "phishing"
    assert messages[0].raw_record_id == raw_records[0].id
    assert len(annotations) == 1
    assert (
        annotations[0].label_source
        == AnnotationLabelSource.GENERATION_GATED_PROMOTION.value
    )
    assert annotations[0].normalized_message_id == messages[0].id


@pytest.mark.asyncio
async def test_persist_generated_promotion_review_rejects_existing_curated_text(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "run": {
            "generator_name": "certfr_generator",
            "source_name": "certfr_phishing_signal",
        },
        "promoted_samples": [
            {
                "draft_id": "draft-1",
                "variant_index": 0,
                "review_state": "usable",
                "target_label": "phishing",
                "normalized_text": "Objet : Alerte\n\nBonjour,\n\nAction immediate requise.",
                "text_sha256": "generated-hash-rerun",
                "language": "fr",
            }
        ],
    }

    async with session_factory() as session:
        await ReviewPersistenceService.persist_generated_promotion_review(
            session,
            payload,
            pipeline_version="generated_reviewed_promotion_v1",
        )

        with pytest.raises(ValueError, match="already present in curated storage"):
            await ReviewPersistenceService.persist_generated_promotion_review(
                session,
                payload,
                pipeline_version="generated_reviewed_promotion_v1",
            )


@pytest.mark.asyncio
async def test_persist_generation_bundle_with_gated_promotion_stages_all_and_promotes_usable(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "run": {
            "generator_name": "bundle_generator",
            "source_name": "adapted_en_fr",
            "generated_artifact_uri": "tasks/generated-bundle.json",
            "status": "completed",
            "total_draft_count": 2,
            "usable_draft_count": 1,
            "needs_prompt_tuning_count": 0,
            "dropped_draft_count": 1,
        },
        "samples": [
            {
                "draft_id": "draft-usable",
                "variant_index": 0,
                "review_state": "usable",
                "target_label": "phishing",
                "normalized_text": "Objet : Controle\n\nBonjour,\n\nMerci de confirmer.",
                "text_sha256": "bundle-hash-1",
                "language": "fr",
            },
            {
                "draft_id": "draft-drop",
                "variant_index": 0,
                "review_state": "drop",
                "target_label": "phishing",
                "normalized_text": "Objet : Brouillon a rejeter",
                "text_sha256": "bundle-hash-2",
                "language": "fr",
            },
        ],
    }

    async with session_factory() as session:
        result = await ReviewPersistenceService.persist_generation_bundle_with_gated_promotion(
            session,
            payload,
            pipeline_version="generation_gated_promotion_v1",
            report_uri="tasks/generated-bundle.json",
        )
        runs = (await session.execute(select(DataGenerationRun))).scalars().all()
        samples = (await session.execute(select(DataGenerationSample))).scalars().all()
        ingestion_runs = (
            (await session.execute(select(DataIngestionRun))).scalars().all()
        )
        raw_records = (await session.execute(select(DataRawRecord))).scalars().all()
        processing_runs = (
            (await session.execute(select(DataProcessingRun))).scalars().all()
        )
        messages = (
            (await session.execute(select(DataNormalizedMessage))).scalars().all()
        )
        annotations = (await session.execute(select(DataAnnotation))).scalars().all()

    assert result["sample_count"] == 2
    assert result["raw_record_count"] == 1
    assert result["normalized_message_count"] == 1
    assert result["annotation_count"] == 1
    assert len(runs) == 1
    assert len(samples) == 2
    assert len(ingestion_runs) == 1
    assert len(raw_records) == 1
    assert raw_records[0].record_key == "draft-usable:0"
    assert raw_records[0].generation_sample_id is not None
    assert len(processing_runs) == 1
    assert len(messages) == 1
    assert messages[0].text_sha256 == "bundle-hash-1"
    assert len(annotations) == 1
    assert (
        annotations[0].label_source
        == AnnotationLabelSource.GENERATION_GATED_PROMOTION.value
    )


@pytest.mark.asyncio
async def test_persist_generated_promotion_review_links_promoted_raw_record_to_staged_generation_sample(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "run": {
            "generator_name": "adapted_phishing_generator",
            "source_name": "adapted_en_fr",
            "generated_artifact_uri": "tasks/generated-adapted.json",
            "status": "completed",
            "created_at": utc_timestamp().isoformat(),
        },
        "samples": [
            {
                "draft_id": "draft-1",
                "variant_index": 0,
                "review_state": "usable",
                "target_label": "phishing",
                "normalized_text": "Objet : Contrôle\n\nBonjour, merci de vérifier.",
                "text_sha256": "staged-hash-1",
                "language": "fr",
            }
        ],
    }

    async with session_factory() as session:
        stage_result = await ReviewPersistenceService.persist_generation_bundle(
            session,
            payload,
        )
        promotion_result = (
            await ReviewPersistenceService.persist_generated_promotion_review(
                session,
                {
                    "run": payload["run"],
                    "generation_run_id": stage_result["generation_run_id"],
                    "promoted_samples": payload["samples"],
                },
                generation_run_id=stage_result["generation_run_id"],
                pipeline_version="generated_reviewed_promotion_v1",
            )
        )
        raw_records = (await session.execute(select(DataRawRecord))).scalars().all()
        samples = (await session.execute(select(DataGenerationSample))).scalars().all()

    assert promotion_result["raw_record_count"] == 1
    assert len(samples) == 1
    assert len(raw_records) == 1
    assert raw_records[0].generation_sample_id == samples[0].id


@pytest.mark.asyncio
async def test_persist_generated_promotion_review_hydrates_text_from_json_artifact(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "generated-drafts.json"
    artifact_path.write_text(
        json.dumps(
            {
                "drafts": [
                    {
                        "draft_id": "artifact-draft-1",
                        "text_sha256": "artifact-hash-1",
                        "full_text": "Objet : Piece jointe\n\nBonjour,\n\nMerci de verifier la piece jointe.",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    payload = {
        "run": {
            "generator_name": "certfr_signal_synthetic",
            "source_name": "certfr-phishing-signal",
            "generated_artifact_uri": str(artifact_path),
        },
        "promoted_samples": [
            {
                "draft_id": "artifact-draft-1",
                "variant_index": 0,
                "review_state": "usable",
                "target_label": "phishing",
                "text_sha256": "artifact-hash-1",
                "language": "fr",
            }
        ],
    }

    async with session_factory() as session:
        result = await ReviewPersistenceService.persist_generated_promotion_review(
            session,
            payload,
            pipeline_version="generated_reviewed_promotion_v1",
        )
        messages = (
            (await session.execute(select(DataNormalizedMessage))).scalars().all()
        )

    assert result["normalized_message_count"] == 1
    assert len(messages) == 1
    assert messages[0].normalized_text.startswith("Objet : Piece jointe")
