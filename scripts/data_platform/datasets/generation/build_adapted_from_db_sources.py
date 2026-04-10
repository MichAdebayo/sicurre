from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")

from core.config import get_settings
from db.models.lineage import DataRawRecord, DataSourceSystem
from data_platform.services.adaptation import FrenchCulturalAdaptationService
from data_platform.services.generation_staging import GenerationStagingService
from data_platform.services.structured_review_artifact import (
    StructuredReviewArtifactService,
)


def _build_generation_samples(dataframe: pd.DataFrame) -> list[dict[str, object]]:
    return [
        {
            "draft_id": f"adapted-db:{index}",
            "scenario_id": str(row.get("archetype") or "adapted_db"),
            "variant_index": 0,
            "source_name": "adapted_en_fr",
            "parent_source": str(row.get("en_source_dataset") or "unknown"),
            "target_label": "phishing",
            "primary_theme": str(row.get("archetype") or ""),
            "review_state": "usable",
            "review_notes": [],
            "text_sha256": str(row.get("text_hash") or ""),
            "nearest_reference_raw_record_id": (
                str(row.get("en_source_raw_record_id"))
                if row.get("en_source_raw_record_id") not in {None, "", "template_only"}
                else None
            ),
            "nearest_similarity": None,
        }
        for index, row in dataframe.reset_index(drop=True).iterrows()
    ]


async def _load_db_seed_dataframe(source_names: list[str]) -> pd.DataFrame:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    rows: list[dict[str, object]] = []

    async with session_factory() as session:
        query = (
            select(DataRawRecord.id, DataRawRecord.raw_content, DataSourceSystem.name)
            .join(
                DataSourceSystem, DataSourceSystem.id == DataRawRecord.source_system_id
            )
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
        description=(
            "Build a no-write adapted phishing artifact from DB-backed English "
            "phishing sources and stage it as a generation bundle."
        )
    )
    parser.add_argument(
        "--sources",
        type=str,
        default="zefang_phishing",
        help="Comma-separated DB source names to use as English phishing seeds.",
    )
    parser.add_argument("--target-per-archetype", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    parser.add_argument("--bundle-json", type=Path, required=True)
    parser.add_argument("--bundle-md", type=Path, required=True)
    args = parser.parse_args()

    source_names = [name.strip() for name in args.sources.split(",") if name.strip()]
    seed_df = await _load_db_seed_dataframe(source_names)
    service = FrenchCulturalAdaptationService(seed=args.seed)
    matched_df = service.attach_archetype_matches(seed_df)
    generated_df = service.generate_all_adapted_emails(
        matched_df,
        target_per_archetype=args.target_per_archetype,
    )
    deduplicated_df, removed_duplicates = service.deduplicate_generated(generated_df)
    summary = service.build_summary(
        seed_df,
        matched_df,
        deduplicated_df,
        removed_duplicates=removed_duplicates,
    )
    export_result = service.export_adapted_dataframe(
        deduplicated_df,
        args.output_csv.parent,
    )
    if export_result.stable_path != args.output_csv:
        args.output_csv.write_text(
            export_result.stable_path.read_text(encoding="utf-8"), encoding="utf-8"
        )

    summary_payload = {
        "mode": "db_backed_adapted_generation_review",
        "sources": source_names,
        "target_per_archetype": args.target_per_archetype,
        "seed_row_count": len(seed_df),
        "matched_row_count": summary.matched_rows,
        "matched_ratio": summary.matched_ratio,
        "generated_row_count": summary.deduplicated_rows,
        "removed_duplicates": summary.removed_duplicates,
        "per_archetype_matches": summary.per_archetype_matches,
        "generated_per_archetype": summary.generated_per_archetype,
        "stable_csv_uri": str(args.output_csv),
    }
    StructuredReviewArtifactService.write_json(args.summary_json, summary_payload)

    bundle = GenerationStagingService.build_bundle(
        generator_name="db_backed_adapted_phishing",
        source_name="adapted_en_fr",
        parent_source=",".join(source_names),
        reference_selection_mode="db_phishing_seed_match",
        input_artifact_uri=str(args.summary_json),
        generated_artifact_uri=str(args.output_csv),
        samples=_build_generation_samples(deduplicated_df),
    )
    StructuredReviewArtifactService.write_json(args.bundle_json, bundle)
    args.bundle_md.parent.mkdir(parents=True, exist_ok=True)
    args.bundle_md.write_text(
        GenerationStagingService.render_markdown(bundle),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {"summary": summary_payload, "bundle": bundle}, ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
