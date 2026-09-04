from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

import pandas as pd
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.config import get_settings
from data_platform.services.shared.generation_staging import GenerationStagingService
from data_platform.services.shared.review_persistence import ReviewPersistenceService


def _resolved_run_timestamp(run_timestamp: str | None) -> str:
    return run_timestamp or datetime.now(UTC).isoformat()


def _coerce_source_parent(values: list[str]) -> str | None:
    normalized_values = sorted(
        {value for value in values if value and value != "unknown"}
    )
    if not normalized_values:
        return None
    return ",".join(normalized_values)


def build_adapted_generation_bundle(
    dataframe: pd.DataFrame,
    *,
    run_timestamp: str | None = None,
    input_artifact_uri: str | None = None,
    generated_artifact_uri: str | None = None,
    generator_name: str = "adapted_phishing_generator",
    source_name: str = "adapted_en_fr",
) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    parent_sources: list[str] = []
    for index, row in dataframe.reset_index(drop=True).iterrows():
        parent_source = str(row.get("en_source_dataset") or "").strip() or None
        if parent_source:
            parent_sources.append(parent_source)

        samples.append(
            {
                "draft_id": f"adapted:{index}",
                "scenario_id": str(row.get("archetype") or "adapted_en_fr"),
                "variant_index": 0,
                "source_name": source_name,
                "parent_source": parent_source,
                "target_label": "phishing",
                "primary_theme": str(row.get("archetype") or ""),
                "review_state": "usable",
                "review_notes": [],
                "text_sha256": str(
                    row.get("text_hash")
                    or sha256(str(row.get("text") or "").encode("utf-8")).hexdigest()
                ),
                "normalized_text": str(row.get("text") or ""),
                "language": str(row.get("language") or "fr"),
                "en_source_raw_record_id": row.get("en_source_raw_record_id"),
            }
        )

    return GenerationStagingService.build_bundle(
        generator_name=generator_name,
        source_name=source_name,
        parent_source=_coerce_source_parent(parent_sources),
        reference_selection_mode="adapted_seed_generation",
        input_artifact_uri=input_artifact_uri,
        generated_artifact_uri=generated_artifact_uri,
        generated_at=_resolved_run_timestamp(run_timestamp),
        samples=samples,
    )


async def persist_generation_bundle_payload(
    payload: dict[str, Any],
    *,
    promote_usable: bool,
    pipeline_version: str,
    report_uri: str | None = None,
    source_system_name: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    engine = create_async_engine(settings.data_platform_database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            if promote_usable:
                return await ReviewPersistenceService.persist_generation_bundle_with_gated_promotion(
                    session,
                    payload,
                    pipeline_version=pipeline_version,
                    report_uri=report_uri,
                    source_system_name=source_system_name,
                )
            return await ReviewPersistenceService.persist_generation_bundle(
                session,
                payload,
            )
    finally:
        await engine.dispose()
