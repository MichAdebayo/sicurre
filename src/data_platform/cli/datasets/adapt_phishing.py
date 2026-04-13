from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from dotenv import load_dotenv

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
    persist_generation_bundle_payload,
)


async def _load_db_seed_dataframe(source_names: list[str]) -> pd.DataFrame:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    rows: list[dict[str, object]] = []

    async with session_factory() as session:
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
            if text := str(payload.get("text") or "").strip():
                rows.append(
                    {
                        "raw_record_id": str(raw_record_id),
                        "text": text,
                        "label": 1,
                        "source": str(source_name),
                    }
                )

    await engine.dispose()
    return pd.DataFrame(rows)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate culturally adapted French phishing emails from an English phishing corpus"
    )
    parser.add_argument(
        "--corpus-path",
        type=Path,
        default=Path("data/raw/csv/en/combined_final_clean.csv"),
        help="Input English phishing corpus CSV",
    )
    parser.add_argument(
        "--db-sources",
        type=str,
        default=None,
        help="Comma-separated DB source names to use as phishing seed records instead of a CSV corpus.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw/db"),
        help="Output directory for adapted CSV exports",
    )
    parser.add_argument(
        "--target-per-archetype",
        type=int,
        default=DEFAULT_TARGET_PER_ARCHETYPE,
        help="Number of French adapted emails to generate per archetype",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic seed for Faker and template selection",
    )
    parser.add_argument(
        "--persist-lineage",
        action="store_true",
        help="Persist the generated run and samples into data_generation_run/data_generation_sample.",
    )
    parser.add_argument(
        "--promote-usable",
        action="store_true",
        help="After staging lineage, promote usable samples into curated storage.",
    )
    parser.add_argument(
        "--pipeline-version",
        type=str,
        default="adapted_generation_v1",
        help="Pipeline version to stamp when usable samples are promoted.",
    )
    parser.add_argument(
        "--run-timestamp",
        type=str,
        default=None,
        help="Explicit ISO timestamp for the generation run metadata.",
    )
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Do not write local CSV artifacts; generate in memory only.",
    )
    args = parser.parse_args()

    service = FrenchCulturalAdaptationService(seed=args.seed)
    if args.db_sources:
        source_names = [name.strip() for name in args.db_sources.split(",") if name.strip()]
        source_df = await _load_db_seed_dataframe(source_names)
    else:
        source_names = []
        source_df = service.load_phishing_corpus(args.corpus_path)
    matched_df = service.attach_archetype_matches(source_df)
    generated_df = service.generate_all_adapted_emails(
        matched_df,
        target_per_archetype=args.target_per_archetype,
    )
    deduplicated_df, removed_duplicates = service.deduplicate_generated(generated_df)
    summary = service.build_summary(
        source_df,
        matched_df,
        deduplicated_df,
        removed_duplicates=removed_duplicates,
    )
    export_result = (
        service.export_adapted_dataframe(deduplicated_df, args.output_dir)
        if not args.skip_export
        else None
    )

    lineage_result: dict[str, object] | None = None
    if args.persist_lineage or args.promote_usable:
        bundle = build_adapted_generation_bundle(
            deduplicated_df,
            run_timestamp=args.run_timestamp,
            input_artifact_uri=(str(args.corpus_path) if not args.db_sources else None),
            generated_artifact_uri=(str(export_result.stable_path) if export_result else None),
            source_name="adapted_en_fr",
        )
        if source_names:
            bundle["run"]["parent_source"] = ",".join(source_names)
        lineage_result = await persist_generation_bundle_payload(
            bundle,
            promote_usable=args.promote_usable,
            pipeline_version=args.pipeline_version,
            report_uri=(str(export_result.stable_path) if export_result else None),
        )

    print(f"Corpus rows kept            : {summary.total_rows:,}")
    print(
        f"Matched to >=1 archetype    : {summary.matched_rows:,} ({summary.matched_ratio:.1%})"
    )
    print(f"Generated rows after dedup  : {summary.deduplicated_rows:,}")
    print(f"Removed duplicates          : {summary.removed_duplicates:,}")
    print(f"Mean text length            : {summary.mean_text_length:.0f}")
    print(f"Min French markers          : {summary.min_french_markers}")
    print(f"Mean French markers         : {summary.mean_french_markers:.1f}")
    print(f"Urgency marker ratio        : {summary.urgency_ratio:.1%}")
    print("Per-archetype source matches:")
    for name, count in sorted(summary.per_archetype_matches.items()):
        print(f"  {name:25s} {count:>6d}")
    print("Per-archetype generated rows:")
    for name, count in sorted(summary.generated_per_archetype.items()):
        print(f"  {name:25s} {count:>6d}")
    if export_result is not None:
        print(f"Timestamped export          : {export_result.timestamped_path}")
        print(f"Stable export               : {export_result.stable_path}")
    if lineage_result is not None:
        print(f"Lineage persistence         : {json.dumps(lineage_result, ensure_ascii=False)}")


if __name__ == "__main__":
    asyncio.run(main())
