from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    DataAnnotation,
    DataGenerationRun,
    DataGenerationSample,
    DataNormalizedMessage,
    DataProcessingRun,
    IngestionStatus,
    RedactionStatus,
)


def _parse_datetime(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _parse_uuid(value: Any) -> UUID | None:
    if value in {None, ""}:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


class ReviewPersistenceService:
    @staticmethod
    async def persist_generation_bundle(
        session: AsyncSession,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        run_payload = dict(payload.get("run") or {})
        created_at = _parse_datetime(run_payload.get("created_at")) or datetime.now(
            timezone.utc
        )
        generation_run = DataGenerationRun(
            generator_name=str(run_payload.get("generator_name") or "unknown"),
            source_name=str(run_payload.get("source_name") or "unknown"),
            parent_source=run_payload.get("parent_source"),
            reference_selection_mode=run_payload.get("reference_selection_mode"),
            input_artifact_uri=run_payload.get("input_artifact_uri"),
            generated_artifact_uri=run_payload.get("generated_artifact_uri"),
            comparison_artifact_uri=run_payload.get("comparison_artifact_uri"),
            monitor_artifact_uri=run_payload.get("monitor_artifact_uri"),
            status=str(run_payload.get("status") or IngestionStatus.COMPLETED.value),
            total_draft_count=int(run_payload.get("total_draft_count") or 0),
            usable_draft_count=int(run_payload.get("usable_draft_count") or 0),
            needs_prompt_tuning_count=int(
                run_payload.get("needs_prompt_tuning_count") or 0
            ),
            dropped_draft_count=int(run_payload.get("dropped_draft_count") or 0),
            created_at=created_at,
            started_at=_parse_datetime(run_payload.get("started_at")) or created_at,
            finished_at=_parse_datetime(run_payload.get("finished_at")) or created_at,
        )
        session.add(generation_run)
        await session.flush()

        samples = list(payload.get("samples") or [])
        for sample_payload in samples:
            session.add(
                DataGenerationSample(
                    generation_run_id=generation_run.id,
                    draft_id=str(sample_payload.get("draft_id") or ""),
                    scenario_id=sample_payload.get("scenario_id"),
                    variant_index=int(sample_payload.get("variant_index") or 0),
                    source_name=str(
                        sample_payload.get("source_name") or generation_run.source_name
                    ),
                    parent_source=sample_payload.get("parent_source"),
                    target_label=str(sample_payload.get("target_label") or "unknown"),
                    primary_theme=sample_payload.get("primary_theme"),
                    review_state=str(sample_payload.get("review_state") or "usable"),
                    review_notes=list(sample_payload.get("review_notes") or []),
                    text_sha256=sample_payload.get("text_sha256"),
                    nearest_reference_raw_record_id=_parse_uuid(
                        sample_payload.get("nearest_reference_raw_record_id")
                    ),
                    nearest_similarity=(
                        float(sample_payload["nearest_similarity"])
                        if sample_payload.get("nearest_similarity") is not None
                        else None
                    ),
                    created_at=_parse_datetime(sample_payload.get("created_at"))
                    or created_at,
                )
            )

        await session.commit()
        return {
            "generation_run_id": str(generation_run.id),
            "sample_count": len(samples),
            "status": generation_run.status,
        }

    @staticmethod
    async def persist_common_crawl_acceptance_review(
        session: AsyncSession,
        payload: dict[str, Any],
        *,
        pipeline_version: str,
        report_uri: str | None = None,
    ) -> dict[str, Any]:
        accepted_candidates = list(payload.get("accepted_candidates") or [])
        proposed_messages = list(payload.get("proposed_normalized_messages") or [])
        proposed_annotations = list(payload.get("proposed_annotations") or [])
        started_at = datetime.now(timezone.utc)

        processing_run = DataProcessingRun(
            pipeline_version=pipeline_version,
            started_at=started_at,
            finished_at=started_at,
            status=IngestionStatus.COMPLETED.value,
            normalized_count=len(proposed_messages),
            rejected_count=int(payload.get("rejected_candidate_count") or 0),
            report_uri=report_uri,
        )
        session.add(processing_run)
        await session.flush()

        annotations_by_candidate_id = {
            str(annotation["candidate_id"]): annotation
            for annotation in proposed_annotations
        }
        created_messages: list[tuple[str, DataNormalizedMessage]] = []

        for candidate, message_payload in zip(
            accepted_candidates, proposed_messages, strict=True
        ):
            message = DataNormalizedMessage(
                raw_record_id=_parse_uuid(message_payload.get("raw_record_id")),
                processing_run_id=processing_run.id,
                normalized_text=str(message_payload.get("normalized_text") or ""),
                text_sha256=str(message_payload.get("text_sha256") or ""),
                language=str(message_payload.get("language") or "fr"),
                current_label=str(message_payload.get("current_label") or "unknown"),
                contains_pii=bool(message_payload.get("contains_pii") or False),
                redaction_status=str(
                    message_payload.get("redaction_status")
                    or RedactionStatus.NOT_REQUIRED.value
                ),
                text_length=int(
                    message_payload.get("text_length")
                    or len(str(message_payload.get("normalized_text") or ""))
                ),
                normalized_at=started_at,
            )
            session.add(message)
            created_messages.append((str(candidate.get("candidate_id") or ""), message))

        await session.flush()

        annotation_count = 0
        for candidate_id, message in created_messages:
            annotation_payload = annotations_by_candidate_id.get(candidate_id)
            if annotation_payload is None:
                continue
            session.add(
                DataAnnotation(
                    normalized_message_id=message.id,
                    label=str(annotation_payload.get("label") or message.current_label),
                    label_source=str(
                        annotation_payload.get("label_source") or "review"
                    ),
                    confidence=(
                        float(annotation_payload["confidence"])
                        if annotation_payload.get("confidence") is not None
                        else None
                    ),
                    comment=annotation_payload.get("comment"),
                    is_validated=bool(annotation_payload.get("is_validated") or False),
                    annotated_at=started_at,
                )
            )
            annotation_count += 1

        await session.commit()
        return {
            "processing_run_id": str(processing_run.id),
            "normalized_message_count": len(created_messages),
            "annotation_count": annotation_count,
            "status": processing_run.status,
        }
