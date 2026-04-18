from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    GenerationReviewState,
    IngestionStatus,
    ObjectType,
    RedactionStatus,
    SourceType,
)
from data_platform.services.common_crawl.promotion_review import (
    CommonCrawlPromotionReviewService,
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


def _try_parse_uuid(value: Any) -> UUID | None:
    try:
        return _parse_uuid(value)
    except (TypeError, ValueError, AttributeError):
        return None


def _text_sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _build_synthetic_source_system_name(
    *, generator_name: str | None, source_name: str | None
) -> str:
    generator_segment = str(generator_name or "generator").strip().replace("_", "-")
    source_segment = str(source_name or "source").strip().replace("_", "-")
    return f"synthetic-generated-{generator_segment}-{source_segment}"


def _normalize_annotation_label_source(
    value: Any,
    *,
    default_value: str,
) -> str:
    resolved_value = str(value or default_value)
    legacy_aliases = {
        "generated_promotion_review": AnnotationLabelSource.GENERATION_GATED_PROMOTION.value,
        "review": AnnotationLabelSource.MANUAL_REVIEW.value,
    }
    return legacy_aliases.get(resolved_value, resolved_value)


def _normalize_generation_source_link_role(
    value: Any,
    *,
    default_value: str,
) -> str:
    resolved_value = str(value or default_value)
    legacy_aliases = {
        "seed": GenerationSourceLinkRole.GENERATION_SEED.value,
        "source_seed": GenerationSourceLinkRole.GENERATION_SEED.value,
        "sample": GenerationSourceLinkRole.SAMPLE_INPUT.value,
        "sampled_record": GenerationSourceLinkRole.SAMPLE_INPUT.value,
        "reference": GenerationSourceLinkRole.NEAREST_REFERENCE.value,
    }
    normalized_value = legacy_aliases.get(resolved_value, resolved_value)
    if normalized_value not in {item.value for item in GenerationSourceLinkRole}:
        raise ValueError(f"Unsupported generation source link role: {resolved_value}")
    return normalized_value


def _append_generation_source_link(
    links: list[dict[str, Any]],
    seen: set[tuple[UUID, str]],
    *,
    raw_record_id: Any,
    link_role: str,
    link_order: int,
) -> None:
    parsed_raw_record_id = _try_parse_uuid(raw_record_id)
    if parsed_raw_record_id is None:
        return

    dedupe_key = (parsed_raw_record_id, link_role)
    if dedupe_key in seen:
        return

    seen.add(dedupe_key)
    links.append(
        {
            "raw_record_id": parsed_raw_record_id,
            "link_role": link_role,
            "link_order": link_order,
        }
    )


def _collect_generation_source_links(
    sample_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    seen: set[tuple[UUID, str]] = set()
    next_order = 0

    explicit_links = sample_payload.get("source_links") or []
    if isinstance(explicit_links, list):
        for explicit_link in explicit_links:
            if not isinstance(explicit_link, dict):
                continue
            link_role = _normalize_generation_source_link_role(
                explicit_link.get("link_role"),
                default_value=GenerationSourceLinkRole.SAMPLE_INPUT.value,
            )
            link_order = int(explicit_link.get("link_order") or next_order)
            before_count = len(links)
            _append_generation_source_link(
                links,
                seen,
                raw_record_id=explicit_link.get("raw_record_id"),
                link_role=link_role,
                link_order=link_order,
            )
            if len(links) > before_count:
                next_order = max(next_order, link_order + 1)

    for field_name in (
        "source_raw_record_id",
        "en_source_raw_record_id",
        "raw_record_id",
    ):
        before_count = len(links)
        _append_generation_source_link(
            links,
            seen,
            raw_record_id=sample_payload.get(field_name),
            link_role=GenerationSourceLinkRole.GENERATION_SEED.value,
            link_order=next_order,
        )
        if len(links) > before_count:
            next_order += 1

    for field_name in ("source_raw_record_ids", "sampled_record_ids"):
        raw_record_ids = sample_payload.get(field_name) or []
        if not isinstance(raw_record_ids, (list, tuple)):
            continue
        for raw_record_id in raw_record_ids:
            before_count = len(links)
            _append_generation_source_link(
                links,
                seen,
                raw_record_id=raw_record_id,
                link_role=GenerationSourceLinkRole.SAMPLE_INPUT.value,
                link_order=next_order,
            )
            if len(links) > before_count:
                next_order += 1

    before_count = len(links)
    _append_generation_source_link(
        links,
        seen,
        raw_record_id=sample_payload.get("nearest_reference_raw_record_id"),
        link_role=GenerationSourceLinkRole.NEAREST_REFERENCE.value,
        link_order=next_order,
    )
    if len(links) > before_count:
        next_order += 1

    return links


def _coalesce_generated_text(payload: dict[str, Any]) -> str:
    direct_text = str(
        payload.get("normalized_text")
        or payload.get("full_text")
        or payload.get("generated_text")
        or payload.get("raw_content")
        or payload.get("text")
        or ""
    )
    if direct_text:
        return direct_text

    subject = str(payload.get("subject") or "").strip()
    body = str(payload.get("body") or "").strip()
    if subject and body:
        return f"Objet : {subject}\n\n{body}"
    return body or subject


def _resolve_generated_artifact_path(run_payload: dict[str, Any]) -> Path | None:
    artifact_uri = str(run_payload.get("generated_artifact_uri") or "").strip()
    if not artifact_uri:
        return None

    artifact_path = Path(artifact_uri)
    if artifact_path.is_absolute():
        return artifact_path

    for base_dir in (Path.cwd(), Path.cwd().parent):
        candidate = (base_dir / artifact_path).resolve()
        if candidate.exists():
            return candidate
    return artifact_path.resolve()


def _load_generated_text_index(
    run_payload: dict[str, Any],
) -> dict[str, dict[str, str]]:
    artifact_path = _resolve_generated_artifact_path(run_payload)
    if artifact_path is None or not artifact_path.exists():
        return {"draft_id": {}, "text_sha256": {}}

    draft_index: dict[str, str] = {}
    hash_index: dict[str, str] = {}
    suffix = artifact_path.suffix.lower()

    if suffix == ".json":
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        rows = []
        for key in ("drafts", "samples", "candidates"):
            value = payload.get(key)
            if isinstance(value, list):
                rows = value
                break
        for row in rows:
            if not isinstance(row, dict):
                continue
            resolved_text = _coalesce_generated_text(row)
            if not resolved_text:
                continue
            draft_id = str(row.get("draft_id") or "").strip()
            text_hash = str(row.get("text_sha256") or "").strip()
            if draft_id:
                draft_index[draft_id] = resolved_text
            if text_hash:
                hash_index[text_hash] = resolved_text

    if suffix == ".csv":
        with artifact_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                resolved_text = _coalesce_generated_text(row)
                if not resolved_text:
                    continue
                draft_id = str(row.get("draft_id") or "").strip()
                text_hash = str(
                    row.get("text_sha256") or row.get("text_hash") or ""
                ).strip()
                if draft_id:
                    draft_index[draft_id] = resolved_text
                if text_hash:
                    hash_index[text_hash] = resolved_text

    return {"draft_id": draft_index, "text_sha256": hash_index}


def _hydrate_sample_text(
    sample_payload: dict[str, Any],
    generated_text_index: dict[str, dict[str, str]],
) -> str:
    direct_text = _coalesce_generated_text(sample_payload)
    if direct_text:
        return direct_text

    draft_id = str(sample_payload.get("draft_id") or "").strip()
    if draft_id:
        resolved = generated_text_index["draft_id"].get(draft_id)
        if resolved:
            return resolved

    text_hash = str(sample_payload.get("text_sha256") or "").strip()
    if text_hash:
        resolved = generated_text_index["text_sha256"].get(text_hash)
        if resolved:
            return resolved

    return ""


class ReviewPersistenceService:
    @staticmethod
    async def _load_generation_sample_index(
        session: AsyncSession,
        *,
        generation_run_id: UUID,
    ) -> dict[tuple[str, int], UUID]:
        rows = (
            (
                await session.execute(
                    select(DataGenerationSample).where(
                        DataGenerationSample.generation_run_id == generation_run_id
                    )
                )
            )
            .scalars()
            .all()
        )
        return {
            (sample.draft_id, int(sample.variant_index)): sample.id for sample in rows
        }

    @staticmethod
    async def _get_or_create_source_system(
        session: AsyncSession,
        *,
        source_system_name: str,
        description: str,
    ) -> DataSourceSystem:
        source_system = (
            await session.execute(
                select(DataSourceSystem).where(
                    DataSourceSystem.name == source_system_name
                )
            )
        ).scalar_one_or_none()
        if source_system is not None:
            return source_system

        source_system = DataSourceSystem(
            name=source_system_name,
            source_type=SourceType.MANUAL.value,
            description=description,
            owner_name="data-platform",
            legal_basis="synthetic_reviewed_generation",
            contains_personal_data=False,
            retention_days=365,
            is_active=True,
        )
        session.add(source_system)
        await session.flush()
        return source_system

    @staticmethod
    async def persist_generation_bundle(
        session: AsyncSession,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        generation_run, samples = (
            await ReviewPersistenceService._stage_generation_bundle(
                session,
                payload,
            )
        )

        await session.commit()
        return {
            "generation_run_id": str(generation_run.id),
            "sample_count": len(samples),
            "status": generation_run.status,
        }

    @staticmethod
    async def _stage_generation_bundle(
        session: AsyncSession,
        payload: dict[str, Any],
    ) -> tuple[DataGenerationRun, list[dict[str, Any]]]:
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
        staged_samples: list[tuple[dict[str, Any], DataGenerationSample]] = []
        for sample_payload in samples:
            generation_sample = DataGenerationSample(
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
            session.add(generation_sample)
            staged_samples.append((sample_payload, generation_sample))

        await session.flush()

        for sample_payload, generation_sample in staged_samples:
            for link_payload in _collect_generation_source_links(sample_payload):
                session.add(
                    DataGenerationSampleSourceLink(
                        generation_sample_id=generation_sample.id,
                        raw_record_id=link_payload["raw_record_id"],
                        link_role=link_payload["link_role"],
                        link_order=link_payload["link_order"],
                        created_at=_parse_datetime(sample_payload.get("created_at"))
                        or created_at,
                    )
                )

        await session.flush()
        return generation_run, samples

    @staticmethod
    def _select_promoted_samples(
        payload: dict[str, Any],
        *,
        auto_promote_usable: bool,
    ) -> tuple[list[dict[str, Any]], set[str]]:
        candidate_samples = list(
            payload.get("promoted_samples") or payload.get("samples") or []
        )
        if not candidate_samples:
            raise ValueError("Promotion payload must include promoted_samples.")

        selected_draft_ids = {
            str(draft_id) for draft_id in payload.get("selected_draft_ids") or []
        }
        if selected_draft_ids:
            promoted_samples = [
                sample
                for sample in candidate_samples
                if str(sample.get("draft_id") or "") in selected_draft_ids
            ]
        elif auto_promote_usable:
            promoted_samples = [
                sample
                for sample in candidate_samples
                if str(sample.get("review_state") or "")
                == GenerationReviewState.USABLE.value
            ]
        else:
            promoted_samples = candidate_samples

        return promoted_samples, selected_draft_ids

    @staticmethod
    async def persist_generation_bundle_with_gated_promotion(
        session: AsyncSession,
        payload: dict[str, Any],
        *,
        pipeline_version: str,
        report_uri: str | None = None,
        source_system_name: str | None = None,
        annotation_label_source: str = AnnotationLabelSource.GENERATION_GATED_PROMOTION.value,
    ) -> dict[str, Any]:
        generation_run, samples = (
            await ReviewPersistenceService._stage_generation_bundle(
                session,
                payload,
            )
        )

        promotable_samples = [
            sample
            for sample in samples
            if str(sample.get("review_state") or "")
            == GenerationReviewState.USABLE.value
        ]
        if not promotable_samples:
            await session.commit()
            return {
                "generation_run_id": str(generation_run.id),
                "sample_count": len(samples),
                "source_system_id": None,
                "ingestion_run_id": None,
                "processing_run_id": None,
                "raw_record_count": 0,
                "normalized_message_count": 0,
                "annotation_count": 0,
                "status": generation_run.status,
            }

        promotion_result = (
            await ReviewPersistenceService.persist_generated_promotion_review(
                session,
                {
                    "run": payload.get("run"),
                    "promoted_samples": promotable_samples,
                },
                pipeline_version=pipeline_version,
                report_uri=report_uri,
                source_system_name=source_system_name,
                generation_run_id=generation_run.id,
                auto_promote_usable=False,
                annotation_label_source=annotation_label_source,
                commit=False,
            )
        )

        await session.commit()
        return {
            "generation_run_id": str(generation_run.id),
            "sample_count": len(samples),
            **promotion_result,
        }

    @staticmethod
    async def persist_generated_promotion_review(
        session: AsyncSession,
        payload: dict[str, Any],
        *,
        pipeline_version: str,
        report_uri: str | None = None,
        source_system_name: str | None = None,
        generation_run_id: UUID | str | None = None,
        auto_promote_usable: bool = False,
        annotation_label_source: str = AnnotationLabelSource.GENERATION_GATED_PROMOTION.value,
        commit: bool = True,
    ) -> dict[str, Any]:
        run_payload = dict(payload.get("run") or {})
        resolved_generation_run_id = _parse_uuid(
            generation_run_id
            or payload.get("generation_run_id")
            or run_payload.get("generation_run_id")
        )
        promoted_samples, selected_draft_ids = (
            ReviewPersistenceService._select_promoted_samples(
                payload,
                auto_promote_usable=auto_promote_usable,
            )
        )

        if not promoted_samples:
            raise ValueError("No promoted samples matched the selected draft ids.")

        seen_draft_variants: set[tuple[str, int]] = set()
        text_hashes: list[str] = []
        generated_text_index = _load_generated_text_index(run_payload)
        for sample_payload in promoted_samples:
            if str(sample_payload.get("review_state") or "") != "usable":
                raise ValueError("Only usable generated samples can be promoted.")

            draft_variant = (
                str(sample_payload.get("draft_id") or ""),
                int(sample_payload.get("variant_index") or 0),
            )
            if draft_variant in seen_draft_variants:
                raise ValueError("Promotion payload contains duplicate draft variants.")
            seen_draft_variants.add(draft_variant)

            normalized_text = _hydrate_sample_text(sample_payload, generated_text_index)
            if not normalized_text:
                raise ValueError("Promoted samples must include generated text.")

            text_hash = str(
                sample_payload.get("text_sha256") or _text_sha256(normalized_text)
            )
            text_hashes.append(text_hash)
            sample_payload.setdefault("normalized_text", normalized_text)
            sample_payload.setdefault("text_sha256", text_hash)

        existing_hashes = {
            row[0]
            for row in (
                await session.execute(
                    select(DataNormalizedMessage.text_sha256).where(
                        DataNormalizedMessage.text_sha256.in_(text_hashes)
                    )
                )
            ).all()
        }
        if existing_hashes:
            raise ValueError(
                "Promotion payload contains texts already present in curated storage."
            )

        generation_sample_index: dict[tuple[str, int], UUID] = {}
        if resolved_generation_run_id is not None:
            generation_sample_index = (
                await ReviewPersistenceService._load_generation_sample_index(
                    session,
                    generation_run_id=resolved_generation_run_id,
                )
            )
            missing_variants = [
                (
                    str(sample_payload.get("draft_id") or ""),
                    int(sample_payload.get("variant_index") or 0),
                )
                for sample_payload in promoted_samples
                if (
                    str(sample_payload.get("draft_id") or ""),
                    int(sample_payload.get("variant_index") or 0),
                )
                not in generation_sample_index
            ]
            if missing_variants:
                raise ValueError(
                    "Promotion payload references draft variants that are not staged in the provided generation run."
                )

        started_at = datetime.now(timezone.utc)
        resolved_source_system_name = (
            source_system_name
            or _build_synthetic_source_system_name(
                generator_name=run_payload.get("generator_name"),
                source_name=run_payload.get("source_name"),
            )
        )
        source_system = await ReviewPersistenceService._get_or_create_source_system(
            session,
            source_system_name=resolved_source_system_name,
            description=(
                "Promoted reviewed generated samples persisted through the synthetic "
                "raw-lineage bridge."
            ),
        )

        ingestion_run = DataIngestionRun(
            source_system_id=source_system.id,
            started_at=started_at,
            finished_at=started_at,
            status=IngestionStatus.COMPLETED.value,
            trigger_mode="promotion",
            raw_object_count=1,
            raw_record_count=len(promoted_samples),
            log_message=report_uri,
        )
        session.add(ingestion_run)
        await session.flush()

        batch_hash = _text_sha256("|".join(sorted(text_hashes)))
        raw_object = DataRawObject(
            ingestion_run_id=ingestion_run.id,
            external_ref=(
                report_uri
                or run_payload.get("generated_artifact_uri")
                or f"{pipeline_version}:{resolved_source_system_name}"
            ),
            object_type=ObjectType.API_PAYLOAD.value,
            storage_uri=run_payload.get("generated_artifact_uri"),
            source_format="generated_promotion_review",
            content_hash=batch_hash,
            source_metadata={
                "generator_name": run_payload.get("generator_name"),
                "source_name": run_payload.get("source_name"),
                "generation_run_id": (
                    str(resolved_generation_run_id)
                    if resolved_generation_run_id is not None
                    else None
                ),
                "selected_draft_ids": sorted(selected_draft_ids),
                "promoted_sample_count": len(promoted_samples),
            },
            collected_at=started_at,
        )
        session.add(raw_object)
        await session.flush()

        raw_records: list[tuple[dict[str, Any], DataRawRecord]] = []
        for sample_payload in promoted_samples:
            draft_variant = (
                str(sample_payload.get("draft_id") or ""),
                int(sample_payload.get("variant_index") or 0),
            )
            raw_record = DataRawRecord(
                raw_object_id=raw_object.id,
                source_system_id=source_system.id,
                generation_sample_id=generation_sample_index.get(draft_variant),
                record_key=(
                    f"{sample_payload.get('draft_id') or 'draft'}:"
                    f"{int(sample_payload.get('variant_index') or 0)}"
                ),
                raw_content=str(sample_payload["normalized_text"]),
                detected_language=str(sample_payload.get("language") or "fr"),
                is_usable=True,
                extracted_at=started_at,
            )
            session.add(raw_record)
            raw_records.append((sample_payload, raw_record))

        processing_run = DataProcessingRun(
            pipeline_version=pipeline_version,
            started_at=started_at,
            finished_at=started_at,
            status=IngestionStatus.COMPLETED.value,
            normalized_count=len(promoted_samples),
            rejected_count=0,
            report_uri=report_uri,
        )
        session.add(processing_run)
        await session.flush()

        created_messages: list[tuple[dict[str, Any], DataNormalizedMessage]] = []
        for sample_payload, raw_record in raw_records:
            message = DataNormalizedMessage(
                raw_record_id=raw_record.id,
                processing_run_id=processing_run.id,
                normalized_text=str(sample_payload["normalized_text"]),
                text_sha256=str(sample_payload["text_sha256"]),
                language=str(sample_payload.get("language") or "fr"),
                current_label=str(
                    sample_payload.get("current_label")
                    or sample_payload.get("target_label")
                    or "unknown"
                ),
                quality_score=(
                    float(sample_payload["quality_score"])
                    if sample_payload.get("quality_score") is not None
                    else None
                ),
                contains_pii=bool(sample_payload.get("contains_pii") or False),
                redaction_status=str(
                    sample_payload.get("redaction_status")
                    or RedactionStatus.NOT_REQUIRED.value
                ),
                text_length=int(
                    sample_payload.get("text_length")
                    or len(str(sample_payload["normalized_text"]))
                ),
                normalized_at=started_at,
            )
            session.add(message)
            created_messages.append((sample_payload, message))

        await session.flush()

        annotation_count = 0
        for sample_payload, message in created_messages:
            annotation_payload = dict(sample_payload.get("annotation") or {})
            session.add(
                DataAnnotation(
                    normalized_message_id=message.id,
                    label=str(annotation_payload.get("label") or message.current_label),
                    label_source=_normalize_annotation_label_source(
                        annotation_payload.get("label_source"),
                        default_value=annotation_label_source,
                    ),
                    confidence=(
                        float(annotation_payload["confidence"])
                        if annotation_payload.get("confidence") is not None
                        else None
                    ),
                    comment=annotation_payload.get("comment")
                    or "Pending curated validation.",
                    is_validated=bool(annotation_payload.get("is_validated") or False),
                    annotated_at=started_at,
                )
            )
            annotation_count += 1

        if commit:
            await session.commit()
        return {
            "source_system_id": str(source_system.id),
            "ingestion_run_id": str(ingestion_run.id),
            "processing_run_id": str(processing_run.id),
            "raw_record_count": len(raw_records),
            "normalized_message_count": len(created_messages),
            "annotation_count": annotation_count,
            "status": processing_run.status,
        }

    @staticmethod
    async def persist_common_crawl_reviewed_export(
        session: AsyncSession,
        export_payload: dict[str, Any],
        *,
        pipeline_version: str,
        report_uri: str | None = None,
    ) -> dict[str, Any]:
        acceptance_review = CommonCrawlPromotionReviewService.build_acceptance_review(
            export_payload
        )
        persistence_result = (
            await ReviewPersistenceService.persist_common_crawl_acceptance_review(
                session,
                acceptance_review,
                pipeline_version=pipeline_version,
                report_uri=report_uri,
            )
        )
        return {
            **persistence_result,
            "reviewed_candidate_count": int(
                acceptance_review.get("reviewed_candidate_count") or 0
            ),
            "accepted_candidate_count": int(
                acceptance_review.get("accepted_candidate_count") or 0
            ),
            "rejected_candidate_count": int(
                acceptance_review.get("rejected_candidate_count") or 0
            ),
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
                    label_source=_normalize_annotation_label_source(
                        annotation_payload.get("label_source"),
                        default_value=AnnotationLabelSource.COMMON_CRAWL_ACCEPTANCE_REVIEW.value,
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
