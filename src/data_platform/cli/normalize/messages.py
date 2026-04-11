from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

load_dotenv(ROOT_DIR / ".env")

from core.config import get_settings  # noqa: E402
from data_platform.services.normalization_pipeline import (
    NormalizationPipeline,
)  # noqa: E402
from data_platform.services.structured_review_artifact import (  # noqa: E402
    StructuredReviewArtifactService,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)


def _render_dry_run_markdown(
    result: dict,
    source_name: str | None,
    batch_size: int,
) -> str:
    title_source = source_name or "all-normalizable-sources"
    lines = [
        "# Normalization Dry Run Review",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"- Source filter: {title_source}",
        f"- Batch size: {batch_size}",
        f"- Records examined: {result.get('processed')}",
        "",
    ]
    if samples := result.get("samples", []):
        lines.extend(["## Produced Samples", ""])
        for index, sample in enumerate(samples, start=1):
            lines.extend(
                [
                    f"### Sample {index}",
                    f"- Source: {sample['source']}",
                    f"- Lane: {sample['lane']}",
                    f"- Route Outcome: {sample['route_outcome']}",
                    f"- Route Subtype: {sample['route_subtype']}",
                    f"- Route Reason: {sample['route_reason']}",
                    f"- Label: {sample['extracted_label']}",
                    f"- Contains PII Tokens: {sample['contains_pii']}",
                    f"- Redaction Status: {sample['redaction_status']}",
                    f"- Trace: {sample['trace_summary']}",
                    "",
                    "#### Before",
                    "",
                    sample["raw_preview"] or "(empty)",
                    "",
                    "#### After",
                    "",
                    sample["normalized_preview"] or "(empty)",
                    "",
                ]
            )
    if rejections := result.get("rejections", []):
        lines.extend(["## Rejected Samples", ""])
        for index, sample in enumerate(rejections, start=1):
            lines.extend(
                [
                    f"### Rejection {index}",
                    f"- Source: {sample['source']}",
                    f"- Lane: {sample['lane']}",
                    f"- Route Outcome: {sample['route_outcome']}",
                    f"- Route Subtype: {sample['route_subtype']}",
                    f"- Route Reason: {sample['route_reason']}",
                    f"- Rejection Reason: {sample['rejection_reason']}",
                    f"- Trace: {sample['trace_summary']}",
                    "",
                    "#### Before",
                    "",
                    sample["raw_preview"] or "(empty)",
                    "",
                ]
            )
    if skipped_reasons := result.get("skipped_reasons", {}):
        lines.extend(["## Skip Summary", ""])
        lines.extend(
            f"- {reason}: {count}" for reason, count in skipped_reasons.items()
        )
        lines.append("")
    return "\n".join(lines)


def _render_review_markdown(
    result: dict,
    source_name: str | None,
    source_type: str | None,
    route_subtype_filter: str | None,
) -> str:
    title_target = source_name or source_type or "all-live-sources"
    lines = [
        "# Normalization Route Review",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"- Target: {title_target}",
        f"- Samples per source: {result.get('samples_per_source')}",
        f"- Reviewed source systems: {result.get('reviewed_source_count')}",
        f"- Total sampled records: {result.get('total_sampled')}",
        f"- Route subtype filter: {route_subtype_filter or 'none'}",
        "",
    ]
    for parent_source, source_groups in result.get("parent_sources", {}).items():
        lines.extend([f"## Parent Source: {parent_source}", ""])
        for source_group in source_groups:
            lines.extend(
                [
                    f"### Source: {source_group['source']}",
                    f"- Lane: {source_group['lane']}",
                    f"- Message normalization: {source_group['normalize_messages']}",
                    f"- Policy reason: {source_group['policy_reason']}",
                    f"- Route filter: {source_group['route_filter']}",
                    f"- Route subtype filter: {source_group['route_subtype_filter']}",
                    f"- Samples returned: {source_group['samples_returned']}/{source_group['samples_requested']}",
                    "- Route summary:",
                ]
            )
            lines.extend(
                f"  - {reason}: {count}"
                for reason, count in source_group.get("route_summary", {}).items()
            )
            if subtype_summary := source_group.get("subtype_summary", {}):
                lines.append("- Subtype summary:")
                lines.extend(
                    f"  - {subtype}: {count}"
                    for subtype, count in subtype_summary.items()
                )
            lines.append("- Transformation summary:")
            lines.extend(
                f"  - {strength}: {count}"
                for strength, count in source_group.get(
                    "transformation_summary", {}
                ).items()
            )
            if rejection_summary := source_group.get("rejection_summary", {}):
                lines.append("- Rejection summary:")
                lines.extend(
                    f"  - {reason}: {count}"
                    for reason, count in rejection_summary.items()
                )
            lines.append("")
            for index, sample in enumerate(source_group.get("samples", []), start=1):
                similarity_score = sample.get("similarity_score")
                similarity_text = (
                    f"{similarity_score:.3f}"
                    if isinstance(similarity_score, float)
                    else "n/a"
                )
                lines.extend(
                    [
                        f"#### Sample {index}",
                        f"- Raw record ID: {sample['raw_record_id']}",
                        f"- Route outcome: {sample['route_outcome']}",
                        f"- Route subtype: {sample['route_subtype']}",
                        f"- Detected language: {sample['detected_language']}",
                        f"- Label: {sample['extracted_label']}",
                        f"- Transformation strength: {sample['transformation_strength']}",
                        f"- Similarity score: {similarity_text}",
                        f"- Raw length: {sample['raw_length']}",
                        f"- Normalized length: {sample['normalized_length']}",
                        f"- Contains PII tokens: {sample['contains_pii']}",
                        f"- Redaction status: {sample['redaction_status']}",
                        f"- Policy reason: {sample['policy_reason']}",
                        f"- Route reason: {sample['route_reason']}",
                        f"- Rejection reason: {sample['rejection_reason']}",
                        f"- Trace: {sample['trace_summary']}",
                        "",
                        "##### Before",
                        "",
                        sample["raw_preview"] or "(empty)",
                        "",
                        "##### After",
                        "",
                        sample["normalized_preview"] or "(not produced)",
                        "",
                    ]
                )
    return "\n".join(lines)


if __name__ == "__main__":

    async def _main() -> None:
        parser = argparse.ArgumentParser(
            description="Sicurre DB Normalization Pipeline (Phase 2)"
        )
        parser.add_argument("--batch-size", type=int, default=1000)
        parser.add_argument("--source", type=str, default=None)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--review-output", type=Path, default=None)
        parser.add_argument("--structured-review-output", type=Path, default=None)
        parser.add_argument("--review-live-sources", action="store_true")
        parser.add_argument("--samples-per-source", type=int, default=10)
        parser.add_argument("--source-type", type=str, default=None)
        parser.add_argument("--route-filter", type=str, default=None)
        parser.add_argument("--max-review-samples", type=int, default=25)
        parser.add_argument("--subtype-filter", type=str, default=None)
        args = parser.parse_args()

        settings = get_settings()
        engine = create_async_engine(settings.database_url, echo=False)
        session_maker = async_sessionmaker(
            engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        logger.info("Connecting to database: %s", settings.database_url)

        async with session_maker() as session:
            pipeline = NormalizationPipeline(session)
            if args.review_live_sources:
                result = await pipeline.review_live_sources(
                    samples_per_source=args.samples_per_source,
                    source_system_name=args.source,
                    source_type=args.source_type,
                    route_outcome_filter=args.route_filter,
                    route_subtype_filter=args.subtype_filter,
                    max_kept_samples_per_source=args.max_review_samples,
                )
            else:
                result = await pipeline.run_batch(
                    batch_size=args.batch_size,
                    source_system_name=args.source,
                    dry_run=args.dry_run,
                )

            status = result.get("status")
            if status in {"error", "skipped"}:
                logger.info(
                    result.get(
                        "message",
                        "Normalization run exited without processing records.",
                    )
                )
                await engine.dispose()
                return

            if args.review_live_sources:
                logger.info("--- LIVE SOURCE ROUTE REVIEW ---")
                for parent_source, source_groups in result.get(
                    "parent_sources", {}
                ).items():
                    logger.info("Parent source: %s", parent_source)
                    for source_group in source_groups:
                        logger.info(
                            "Source %s | lane=%s | routes=%s",
                            source_group["source"],
                            source_group["lane"],
                            source_group["route_summary"],
                        )
                if args.review_output:
                    args.review_output.parent.mkdir(parents=True, exist_ok=True)
                    args.review_output.write_text(
                        _render_review_markdown(
                            result,
                            args.source,
                            args.source_type,
                            args.subtype_filter,
                        ),
                        encoding="utf-8",
                    )
                    logger.info("Review output written to %s", args.review_output)
                if args.structured_review_output:
                    StructuredReviewArtifactService.write_json(
                        args.structured_review_output,
                        StructuredReviewArtifactService.build_payload(
                            result=result,
                            source_name=args.source,
                            source_type=args.source_type,
                            route_outcome_filter=args.route_filter,
                            route_subtype_filter=args.subtype_filter,
                        ),
                    )
                    logger.info(
                        "Structured review output written to %s",
                        args.structured_review_output,
                    )
                logger.info("Total reviewed samples: %s", result.get("total_sampled"))
            elif args.dry_run:
                logger.info("--- DRY RUN SAMPLES ---")
                for sample in result.get("samples", []):
                    logger.info("Source: %s", sample["source"])
                    logger.info("Lane: %s", sample["lane"])
                    logger.info("Label: %s", sample["extracted_label"])
                    logger.info("Before: %s", sample["raw_preview"])
                    logger.info("After: %s", sample["normalized_preview"])
                    logger.info("-" * 40)
                for sample in result.get("rejections", []):
                    logger.info("Rejected Source: %s", sample["source"])
                    logger.info("Lane: %s", sample["lane"])
                    logger.info("Reason: %s", sample["rejection_reason"])
                    logger.info("Before: %s", sample["raw_preview"])
                    logger.info("-" * 40)
                if skipped_reasons := result.get("skipped_reasons", {}):
                    logger.info("Skipped during dry run: %s", skipped_reasons)
                if args.review_output:
                    args.review_output.parent.mkdir(parents=True, exist_ok=True)
                    args.review_output.write_text(
                        _render_dry_run_markdown(result, args.source, args.batch_size),
                        encoding="utf-8",
                    )
                    logger.info("Review output written to %s", args.review_output)
                if args.structured_review_output:
                    StructuredReviewArtifactService.write_json(
                        args.structured_review_output,
                        StructuredReviewArtifactService.build_payload(
                            result=result,
                            source_name=args.source,
                            source_type=None,
                            route_outcome_filter=None,
                            route_subtype_filter=None,
                        ),
                    )
                    logger.info(
                        "Structured review output written to %s",
                        args.structured_review_output,
                    )
                logger.info("Total processed in dry run: %s", result.get("processed"))
            else:
                logger.info("Execution complete: %s", result)

        await engine.dispose()

    asyncio.run(_main())
