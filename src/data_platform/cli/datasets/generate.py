from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
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
from data_platform.services.common_crawl.promotion_review import (  # noqa: E402
    CommonCrawlPromotionReviewService,
)
from data_platform.services.common_crawl.signal_synthetic import (  # noqa: E402
    CommonCrawlSignalSyntheticService,
)
from data_platform.services.shared.generation_lineage import (  # noqa: E402
    build_adapted_generation_bundle,
    build_synthetic_generation_bundle,
)
from data_platform.services.shared.generation_staging import (
    GenerationStagingService,
)  # noqa: E402
from data_platform.services.shared.review_persistence import (
    ReviewPersistenceService,
)  # noqa: E402
from data_platform.services.shared.structured_review_artifact import (  # noqa: E402
    StructuredReviewArtifactService,
)
from data_platform.services.shared.synthetic_generation import (  # noqa: E402
    DEFAULT_TARGETS,
    SyntheticGenerationService,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate Sicurre training data fully in memory and persist the full "
            "generation lineage and curated promotion directly to the database.\n\n"
            "Modes:\n"
            "  adapted       — French cultural adaptation from EN phishing seeds\n"
            "  synthetic     — Pure archetype-based synthetic generation\n"
            "  cc-signal     — Common Crawl phishing signal synthetic drafts\n"
            "  cc-acceptance — Common Crawl legit/spam acceptance review\n"
            "  all           — Run adapted + cc-signal + cc-acceptance\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["adapted", "synthetic", "cc-signal", "cc-acceptance", "all"],
        default="all",
        help="Which generation lane to run.",
    )

    # ── Adapted lane ──
    parser.add_argument(
        "--corpus-path",
        type=Path,
        default=Path("data/raw/file/csv/en/combined_final_clean.csv"),
        help="English phishing corpus used for the adapted generation lane.",
    )
    parser.add_argument(
        "--db-sources",
        type=str,
        default=None,
        help="Comma-separated DB source names to use as adapted phishing seeds instead of a CSV corpus.",
    )
    parser.add_argument(
        "--adapted-target-per-archetype",
        type=int,
        default=DEFAULT_TARGET_PER_ARCHETYPE,
        help="Number of adapted phishing rows to generate per archetype.",
    )

    # ── Synthetic lane ──
    parser.add_argument(
        "--synthetic-class",
        choices=["phishing", "spam", "legitimate", "all"],
        default="all",
        help="Synthetic class scope when the synthetic lane runs.",
    )
    parser.add_argument(
        "--synthetic-count",
        type=int,
        default=0,
        help="Rows to generate per selected synthetic class (0 uses per-class defaults).",
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


def _resolve_synthetic_classes(selection: str) -> list[str]:
    return ["phishing", "spam", "legitimate"] if selection == "all" else [selection]


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
    else:
        logger.info("Loading seeds from CSV corpus: %s", args.corpus_path)
        source_df = service.load_phishing_corpus(args.corpus_path)

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


# ── Synthetic lane ────────────────────────────────────────────


async def _run_synthetic_generation(
    session: AsyncSession,
    args: argparse.Namespace,
) -> list[dict[str, object]]:
    logger.info("Starting synthetic archetype generation lane")
    service = SyntheticGenerationService(seed=args.seed)
    output: list[dict[str, object]] = []
    for class_name in _resolve_synthetic_classes(args.synthetic_class):
        count = (
            args.synthetic_count
            if args.synthetic_count > 0
            else DEFAULT_TARGETS.get(class_name, 0)
        )
        result = service.generate_result(class_name, count, export=not args.skip_export)
        persistence: dict[str, object] | None = None
        if not result.dataframe.empty:
            bundle = build_synthetic_generation_bundle(
                result.dataframe,
                class_name=class_name,
                run_timestamp=args.run_timestamp,
            )
            logger.info(
                "Persisting synthetic %s bundle: %d samples",
                class_name,
                len(bundle.get("samples", [])),
            )
            persistence = await _persist_bundle(
                session,
                payload=bundle,
                pipeline_version=args.pipeline_version,
                lineage_only=args.persist_lineage,
            )
        output.append(
            {
                "class_name": class_name,
                "requested_count": count,
                "generated_count": int(len(result.dataframe)),
                "persistence": persistence,
            }
        )
    return output


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


def _load_cc_export(args: argparse.Namespace) -> dict[str, object]:
    """Load the CC evaluated export JSON required by CC modes."""
    if args.cc_export_json is None:
        raise SystemExit(
            "ERROR: --cc-export-json is required for cc-signal, cc-acceptance, and all modes.\n"
            "Generate the export first with the normalization pipeline, then pass the JSON path."
        )
    if not args.cc_export_json.exists():
        raise SystemExit(f"ERROR: CC export JSON not found: {args.cc_export_json}")
    logger.info("Loading CC export from %s", args.cc_export_json)
    return StructuredReviewArtifactService.read_json(args.cc_export_json)


async def main() -> None:
    args = parse_args()
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
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
                cc_export = _load_cc_export(args)

            if args.mode in {"adapted", "all"}:
                output["adapted"] = await _run_adapted_generation(session, args)

            if args.mode == "synthetic":
                output["synthetic"] = await _run_synthetic_generation(session, args)

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
    finally:
        await engine.dispose()

    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
