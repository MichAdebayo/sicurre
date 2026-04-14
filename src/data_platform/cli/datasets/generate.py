from __future__ import annotations

import argparse
import asyncio
import json
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
from data_platform.services.adaptation import (  # noqa: E402
    DEFAULT_TARGET_PER_ARCHETYPE,
    FrenchCulturalAdaptationService,
)
from data_platform.services.generation_lineage import (  # noqa: E402
    build_adapted_generation_bundle,
    build_synthetic_generation_bundle,
)
from data_platform.services.review_persistence import ReviewPersistenceService  # noqa: E402
from data_platform.services.synthetic_generation import (  # noqa: E402
    DEFAULT_TARGETS,
    SyntheticGenerationService,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate Sicurre training data fully in memory and persist the full "
            "generation lineage and curated promotion directly to the database."
        )
    )
    parser.add_argument(
        "--mode",
        choices=["adapted", "synthetic", "all"],
        default="all",
        help="Which generation lane to run.",
    )
    parser.add_argument(
        "--corpus-path",
        type=Path,
        default=Path("data/raw/csv/en/combined_final_clean.csv"),
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
) -> dict[str, object]:
    return await ReviewPersistenceService.persist_generation_bundle_with_gated_promotion(
        session,
        payload,
        pipeline_version=pipeline_version,
    )


async def _run_adapted_generation(
    session: AsyncSession,
    args: argparse.Namespace,
) -> dict[str, object]:
    service = FrenchCulturalAdaptationService(seed=args.seed)
    source_names = [
        name.strip() for name in (args.db_sources or "").split(",") if name.strip()
    ]
    if source_names:
        source_df = await _load_db_seed_dataframe(session, source_names)
    else:
        source_df = service.load_phishing_corpus(args.corpus_path)

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
        persistence = await _persist_bundle(
            session,
            payload=bundle,
            pipeline_version=args.pipeline_version,
        )

    return {
        "seed_count": len(source_df),
        "matched_count": int(summary.matched_rows),
        "generated_count": int(summary.deduplicated_rows),
        "removed_duplicates": int(summary.removed_duplicates),
        "parent_sources": source_names,
        "persistence": persistence,
    }


async def _run_synthetic_generation(
    session: AsyncSession,
    args: argparse.Namespace,
) -> list[dict[str, object]]:
    service = SyntheticGenerationService(seed=args.seed)
    output: list[dict[str, object]] = []
    for class_name in _resolve_synthetic_classes(args.synthetic_class):
        count = args.synthetic_count if args.synthetic_count > 0 else DEFAULT_TARGETS.get(class_name, 0)
        result = service.generate_result(class_name, count, export=False)
        persistence: dict[str, object] | None = None
        if not result.dataframe.empty:
            bundle = build_synthetic_generation_bundle(
                result.dataframe,
                class_name=class_name,
                run_timestamp=args.run_timestamp,
            )
            persistence = await _persist_bundle(
                session,
                payload=bundle,
                pipeline_version=args.pipeline_version,
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
            if args.mode in {"adapted", "all"}:
                output["adapted"] = await _run_adapted_generation(session, args)
            if args.mode in {"synthetic", "all"}:
                output["synthetic"] = await _run_synthetic_generation(session, args)
    finally:
        await engine.dispose()

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())