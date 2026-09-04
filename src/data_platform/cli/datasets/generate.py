from __future__ import annotations

from typing import Any

import argparse
import asyncio
import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

load_dotenv(ROOT_DIR / ".env")

from core.config import get_settings  # noqa: E402
from db.models.lineage import DataRawRecord, DataSourceSystem  # noqa: E402
from data_platform.services.shared.adaptation import (  # noqa: E402
    DEFAULT_TARGET_PER_ARCHETYPE,
    FrenchCulturalAdaptationService,
)
from data_platform.services.common_crawl.signal_synthetic import (  # noqa: E402
    CommonCrawlSignalSyntheticService,
)
from data_platform.services.certfr.lane import (  # noqa: E402
    CERTFR_SOURCE,
    build_certfr_generation_bundle,
)
from data_platform.services.shared.generation_lineage import (  # noqa: E402
    build_adapted_generation_bundle,
)
from data_platform.services.shared.generation_staging import (
    GenerationStagingService,
)  # noqa: E402
from data_platform.services.shared.normalization_pipeline import (
    NormalizationPipeline,
)  # noqa: E402
from data_platform.services.shared.review_persistence import (
    ReviewPersistenceService,
)  # noqa: E402
from data_platform.services.shared.stage_two_action_artifacts import (
    StageTwoActionArtifactsService,
)  # noqa: E402
from data_platform.services.shared.stage_two_reviewed_export import (
    StageTwoReviewedExportService,
)  # noqa: E402
from data_platform.services.shared.stage_two_rewrite_drafts import (
    StageTwoRewriteDraftService,
)  # noqa: E402
from data_platform.services.shared.stage_two_rewrite_jobs import (
    StageTwoRewriteJobService,
)  # noqa: E402
from data_platform.services.shared.structured_review_artifact import (  # noqa: E402
    StructuredReviewArtifactService,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

COMMON_CRAWL_SOURCE_NAME = "common-crawl-bigdata"
ADAPTABLE_SUBTYPES = {
    "instructional_legitimate",
    "awareness_or_report",
    "promotional_spam",
    "phishing_lure_candidate",
}


def _target_from_subtype(route_subtype: str | None) -> str:
    if route_subtype in {
        "transactional_legitimate",
        "instructional_legitimate",
        "awareness_or_report",
    }:
        return "legitimate"
    if route_subtype in {"promotional_spam"}:
        return "spam"
    if route_subtype in {"phishing_lure_candidate"}:
        return "phishing"
    return "holdout"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate Sicurre training data fully in memory and persist the full "
            "generation lineage and curated promotion directly to the database.\n\n"
            "Modes:\n"
            "  adapted       — French cultural adaptation from EN phishing seeds\n"
            "  cc-signal     — Common Crawl phishing signal synthetic drafts\n"
            "  cc-acceptance — Common Crawl legit/spam acceptance review\n"
            "  certfr        — CERT-FR CTI to French phishing drafts\n"
            "  all           — Run adapted + cc-signal + cc-acceptance + certfr\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["adapted", "cc-signal", "cc-acceptance", "certfr", "all"],
        default="all",
        help="Which generation lane to run.",
    )

    # ── Adapted lane ──
    parser.add_argument(
        "--corpus-path",
        type=Path,
        default=None,
        help="Path to a local English phishing CSV corpus. Not required when --db-sources is set.",
    )
    parser.add_argument(
        "--db-sources",
        type=str,
        default="zefang_phishing",
        help="Comma-separated DB source names to use as adapted phishing seeds (default: zefang_phishing).",
    )
    parser.add_argument(
        "--adapted-target-per-archetype",
        type=int,
        default=DEFAULT_TARGET_PER_ARCHETYPE,
        help="Number of adapted phishing rows to generate per archetype.",
    )

    # ── CC lanes ──
    parser.add_argument(
        "--cc-export-json",
        type=Path,
        default=None,
        help=(
            "Path to a pre-built CC evaluated export JSON. "
            "Used by both cc-signal and cc-acceptance modes. "
            "If not provided, the export must be generated separately first."
        ),
    )
    parser.add_argument(
        "--cc-signal-variants-per-seed",
        type=int,
        default=2,
        help="Number of synthetic variants per CC phishing lure seed.",
    )

    # ── Common ──
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic seed for generation services.",
    )
    parser.add_argument(
        "--pipeline-version",
        type=str,
        default="generation_pipeline_v1",
        help="Pipeline version stamped on generated curated rows.",
    )
    parser.add_argument(
        "--run-timestamp",
        type=str,
        default=None,
        help="Explicit ISO timestamp for generation run metadata.",
    )
    parser.add_argument(
        "--persist-lineage",
        action="store_true",
        help="Stage generation lineage without promoting usable samples.",
    )
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Do not write local CSV artifacts; generate in memory only.",
    )
    return parser.parse_args()


async def _load_db_seed_dataframe(
    session: AsyncSession,
    source_names: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    query = (
        select(DataRawRecord.id, DataRawRecord.raw_content, DataSourceSystem.name)
        .join(DataSourceSystem, DataSourceSystem.id == DataRawRecord.source_system_id)
        .where(DataSourceSystem.name.in_(source_names))
    )
    result = await session.execute(query)
    for raw_record_id, raw_content, source_name in result.all():
        payload = json.loads(str(raw_content))
        raw_label = str(payload.get("label") or "").strip().lower()
        if raw_label not in {"1", "phishing"}:
            continue
        text = str(payload.get("text") or "").strip()
        if not text:
            continue
        rows.append(
            {
                "raw_record_id": str(raw_record_id),
                "text": text,
                "label": 1,
                "source": str(source_name),
            }
        )
    return pd.DataFrame(rows)


async def _persist_bundle(
    session: AsyncSession,
    *,
    payload: dict[str, object],
    pipeline_version: str,
    lineage_only: bool = False,
) -> dict[str, object]:
    if lineage_only:
        return await ReviewPersistenceService.persist_generation_bundle(
            session,
            payload,
        )
    return (
        await ReviewPersistenceService.persist_generation_bundle_with_gated_promotion(
            session,
            payload,
            pipeline_version=pipeline_version,
        )
    )


# ── Adapted lane ──────────────────────────────────────────────


async def _run_adapted_generation(
    session: AsyncSession,
    args: argparse.Namespace,
) -> dict[str, object]:
    logger.info("Starting adapted phishing generation lane")
    service = FrenchCulturalAdaptationService(seed=args.seed)
    source_names = [
        name.strip() for name in (args.db_sources or "").split(",") if name.strip()
    ]
    if source_names:
        logger.info("Loading seeds from DB sources: %s", source_names)
        source_df = await _load_db_seed_dataframe(session, source_names)
    elif args.corpus_path is not None:
        logger.info("Loading seeds from CSV corpus: %s", args.corpus_path)
        source_df = service.load_phishing_corpus(args.corpus_path)
    else:
        raise SystemExit(
            "ERROR: Adapted lane requires either --db-sources or --corpus-path."
        )

    logger.info("Seed rows loaded: %d", len(source_df))
    matched_df = service.attach_archetype_matches(source_df)
    generated_df = service.generate_all_adapted_emails(
        matched_df,
        target_per_archetype=args.adapted_target_per_archetype,
    )
    deduplicated_df, removed_duplicates = service.deduplicate_generated(generated_df)
    summary = service.build_summary(
        source_df,
        matched_df,
        deduplicated_df,
        removed_duplicates=removed_duplicates,
    )

    persistence: dict[str, object] | None = None
    if not deduplicated_df.empty:
        bundle = build_adapted_generation_bundle(
            deduplicated_df,
            run_timestamp=args.run_timestamp,
            input_artifact_uri=(str(args.corpus_path) if not source_names else None),
        )
        logger.info(
            "Persisting adapted bundle: %d samples", len(bundle.get("samples", []))
        )
        persistence = await _persist_bundle(
            session,
            payload=bundle,
            pipeline_version=args.pipeline_version,
            lineage_only=args.persist_lineage,
        )

    logger.info(
        "Adapted lane complete: %d generated, %d duplicates removed",
        summary.deduplicated_rows,
        summary.removed_duplicates,
    )
    return {
        "seed_count": len(source_df),
        "matched_count": int(summary.matched_rows),
        "generated_count": int(summary.deduplicated_rows),
        "removed_duplicates": int(summary.removed_duplicates),
        "parent_sources": source_names,
        "persistence": persistence,
    }


# ── CC Signal lane ────────────────────────────────────────────


def _build_cc_signal_generation_bundle(
    drafts_payload: dict[str, object],
) -> dict[str, object]:
    """Convert CommonCrawlSignalSyntheticService.build_drafts() output into
    a generation bundle suitable for persist_generation_bundle_with_gated_promotion."""
    drafts = drafts_payload.get("drafts", [])
    samples: list[dict[str, object]] = []
    for draft in drafts:
        samples.append(
            {
                "draft_id": draft.get("draft_id"),
                "scenario_id": draft.get("scenario_id"),
                "variant_index": draft.get("variant_index", 0),
                "source_name": "common-crawl-phishing-signal",
                "parent_source": "common-crawl-bigdata",
                "target_label": draft.get("target_label", "phishing"),
                "primary_theme": draft.get("primary_theme", ""),
                "review_state": draft.get("review_state", "usable"),
                "review_notes": draft.get("review_notes", []),
                "text_sha256": draft.get("text_sha256", ""),
                "normalized_text": draft.get("normalized_text", ""),
                "language": "fr",
                "nearest_reference_raw_record_id": draft.get(
                    "nearest_reference_raw_record_id"
                ),
                "nearest_similarity": draft.get("nearest_similarity"),
            }
        )

    return GenerationStagingService.build_bundle(
        generator_name="common_crawl_signal_synthetic",
        source_name="common-crawl-phishing-signal",
        parent_source="common-crawl-bigdata",
        reference_selection_mode="reviewed_export_phishing_seed",
        generated_at=str(drafts_payload.get("generated_at", "")),
        samples=samples,
    )


async def _run_certfr_generation(
    session: AsyncSession,
    args: argparse.Namespace,
) -> dict[str, object]:
    """Turn ingested CERT-FR CTI into staged French phishing drafts.

    The four CERT-FR services this composes were built and unit-tested, and none
    of them had a caller: stage_two routed records to a destination nothing
    reached. This lane is that destination, and it reuses the same bundle and
    persistence contract as the adapted and Common Crawl lanes rather than
    introducing a second path.
    """
    records_result = await session.execute(
        select(DataRawRecord)
        .join(DataSourceSystem, DataRawRecord.source_system_id == DataSourceSystem.id)
        .where(
            DataSourceSystem.name == CERTFR_SOURCE,
            DataRawRecord.is_usable.is_(True),
        )
    )
    raw_records = records_result.scalars().all()

    records: list[dict[str, Any]] = []
    for record in raw_records:
        try:
            raw_content = json.loads(record.raw_content)
        except (TypeError, ValueError):
            continue
        records.append(
            {"raw_record_id": str(record.id), "raw_content": raw_content}
        )

    logger.info("CERT-FR lane: %d CTI records loaded", len(records))
    bundle = build_certfr_generation_bundle(records, run_timestamp=args.run_timestamp)
    samples = bundle.get("samples", []) or []

    persistence: dict[str, object] | None = None
    if samples:
        logger.info("Persisting CERT-FR bundle: %d drafts", len(samples))
        persistence = await _persist_bundle(
            session,
            payload=bundle,
            pipeline_version=args.pipeline_version,
            lineage_only=args.persist_lineage,
        )
    else:
        logger.info("CERT-FR lane produced no drafts; nothing to persist.")

    return {
        "cti_records": len(records),
        "generated_count": len(samples),
        "persistence": persistence,
    }


async def _run_cc_signal_generation(
    session: AsyncSession,
    args: argparse.Namespace,
    export_payload: dict[str, object],
) -> dict[str, object]:
    logger.info("Starting CC signal synthetic generation lane")
    drafts_payload = CommonCrawlSignalSyntheticService.build_drafts(
        export_payload,
        variants_per_seed=args.cc_signal_variants_per_seed,
    )
    logger.info(
        "CC signal drafts built: %d total, review=%s",
        drafts_payload.get("draft_count"),
        drafts_payload.get("review_summary"),
    )

    bundle = _build_cc_signal_generation_bundle(drafts_payload)
    logger.info(
        "Persisting CC signal bundle: %d samples", len(bundle.get("samples", []))
    )
    persistence = await _persist_bundle(
        session,
        payload=bundle,
        pipeline_version=args.pipeline_version,
        lineage_only=args.persist_lineage,
    )

    return {
        "seed_count": drafts_payload.get("seed_count"),
        "draft_count": drafts_payload.get("draft_count"),
        "review_summary": drafts_payload.get("review_summary"),
        "persistence": persistence,
    }


# ── CC Acceptance lane ────────────────────────────────────────


async def _run_cc_acceptance(
    session: AsyncSession,
    args: argparse.Namespace,
    export_payload: dict[str, object],
) -> dict[str, object]:
    logger.info("Starting CC acceptance review lane")
    result = await ReviewPersistenceService.persist_common_crawl_reviewed_export(
        session,
        export_payload,
        pipeline_version=args.pipeline_version,
        report_uri=str(args.cc_export_json) if args.cc_export_json else None,
    )
    logger.info(
        "CC acceptance complete: accepted=%s, rejected=%s",
        result.get("accepted_candidate_count"),
        result.get("rejected_candidate_count"),
    )
    return result


# ── Main ──────────────────────────────────────────────────────


async def _load_cc_export_rows_from_db(
    session: AsyncSession,
) -> list[tuple[str, dict[str, object]]]:
    source = await session.scalar(
        select(DataSourceSystem).where(
            DataSourceSystem.name == COMMON_CRAWL_SOURCE_NAME
        )
    )
    if source is None:
        return []

    result = await session.execute(
        select(DataRawRecord.id, DataRawRecord.raw_content)
        .where(
            DataRawRecord.source_system_id == source.id,
            DataRawRecord.is_usable.is_(True),
        )
        .order_by(DataRawRecord.raw_content.asc())
    )
    rows: list[tuple[str, dict[str, object]]] = []
    for raw_record_id, raw_content in result.all():
        payload = json.loads(str(raw_content))
        if isinstance(payload, dict):
            rows.append((str(raw_record_id), payload))
    return rows


def _build_cc_export_from_rows(
    rows: list[tuple[str, dict[str, object]]],
) -> dict[str, object]:
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]
    samples_by_subtype: dict[str, list[dict[str, object]]] = defaultdict(list)

    for raw_record_id, row in rows:
        payload = pipeline.extract_payload(
            COMMON_CRAWL_SOURCE_NAME,
            {
                "text": row.get("text", ""),
                "label": row.get("label"),
                "category": row.get("category"),
                "query": row.get("query"),
                "query_label": row.get("query_label") or row.get("label"),
                "url": row.get("url"),
            },
        )
        route_subtype = payload.route_subtype
        if route_subtype not in ADAPTABLE_SUBTYPES:
            continue

        text = payload.text or ""
        route_target = _target_from_subtype(route_subtype)
        extracted_label = (
            route_target
            if route_target != "holdout"
            else str(
                payload.label.value
                if hasattr(payload.label, "value")
                else payload.label
            )
        )
        samples_by_subtype[route_subtype].append(
            {
                "raw_record_id": raw_record_id,
                "route_outcome": payload.route_outcome,
                "route_subtype": route_subtype,
                "route_reason": payload.route_reason,
                "rejection_reason": payload.rejection_reason,
                "extracted_label": extracted_label,
                "transformation_strength": "major",
                "similarity_score": 0.0,
                "normalized_length": len(text.strip()) if text else 0,
                "normalized_preview": text,
                "trace_summary": " > ".join(payload.trace_steps),
                "derived_payload": payload.derived_payload or {},
                "source_label": row.get("label") or "unknown",
                "source_category": row.get("category") or "unknown",
                "source_url": row.get("url") or "",
            }
        )

    rules: list[dict[str, object]] = []
    for subtype in (
        "instructional_legitimate",
        "awareness_or_report",
        "promotional_spam",
        "phishing_lure_candidate",
    ):
        matching_samples = samples_by_subtype.get(subtype, [])
        if not matching_samples:
            continue

        deduped = StageTwoActionArtifactsService._deduplicate_adaptation_samples(
            matching_samples
        )
        label_summary = Counter(
            str(sample.get("extracted_label") or "unknown") for sample in deduped
        )
        rules.append(
            {
                "source_name": COMMON_CRAWL_SOURCE_NAME,
                "key_type": "route_subtype",
                "key": subtype,
                "action": "adapt",
                "output_bucket": "adaptation_queue",
                "adaptation_fit": "high",
                "rationale": "in_memory_generation",
                "current_count": len(matching_samples),
                "sampled_record_count": len(deduped),
                "sampled_records": deduped,
                "label_summary": dict(label_summary),
            }
        )

    adaptation_queue: dict[str, object] = {
        "mode": "common_crawl_live_three_class_adaptation_queue",
        "sources": [{"source_name": COMMON_CRAWL_SOURCE_NAME, "rules": rules}],
    }
    rewrite_jobs = StageTwoRewriteJobService.build_jobs(adaptation_queue)
    rewrite_drafts = StageTwoRewriteDraftService.build_drafts(rewrite_jobs)
    return StageTwoReviewedExportService().build_export(rewrite_drafts)


async def _load_cc_export(
    session: AsyncSession,
    args: argparse.Namespace,
) -> dict[str, object]:
    """Load the CC evaluated export JSON required by CC modes."""
    if args.cc_export_json is not None:
        if not args.cc_export_json.exists():
            raise SystemExit(f"ERROR: CC export JSON not found: {args.cc_export_json}")
        logger.info("Loading CC export from %s", args.cc_export_json)
        return StructuredReviewArtifactService.read_json(args.cc_export_json)

    logger.info(
        "No --cc-export-json provided; building Common Crawl reviewed export in memory from '%s' DB records",
        COMMON_CRAWL_SOURCE_NAME,
    )
    rows = await _load_cc_export_rows_from_db(session)
    if not rows:
        raise SystemExit(
            "ERROR: No usable common-crawl-bigdata raw records found in DB to build CC export in memory."
        )
    export_payload = _build_cc_export_from_rows(rows)
    logger.info(
        "Built in-memory CC export: candidates=%d label_summary=%s",
        int(export_payload.get("exported_candidate_count") or 0),
        export_payload.get("label_summary"),
    )
    return export_payload


async def main() -> None:
    args = parse_args()
    settings = get_settings()
    engine = create_async_engine(settings.data_platform_database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            output: dict[str, object] = {
                "mode": args.mode,
                "pipeline_version": args.pipeline_version,
                "run_timestamp": args.run_timestamp,
            }

            # Pre-load CC export if needed
            cc_export: dict[str, object] | None = None
            if args.mode in {"cc-signal", "cc-acceptance", "all"}:
                cc_export = await _load_cc_export(session, args)

            if args.mode in {"adapted", "all"}:
                output["adapted"] = await _run_adapted_generation(session, args)

            if args.mode in {"cc-signal", "all"}:
                assert cc_export is not None
                output["cc_signal"] = await _run_cc_signal_generation(
                    session, args, cc_export
                )

            if args.mode in {"cc-acceptance", "all"}:
                assert cc_export is not None
                output["cc_acceptance"] = await _run_cc_acceptance(
                    session, args, cc_export
                )

            if args.mode in {"certfr", "all"}:
                output["certfr"] = await _run_certfr_generation(session, args)
    finally:
        await engine.dispose()

    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
