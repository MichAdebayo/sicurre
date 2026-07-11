from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.trace_logger import SemanticTraceLogger  # noqa: E402
from data_platform.cli.bigdata.common_crawl_extract import (  # noqa: E402
    build_settings,
    run_extraction,
)
from data_platform.cli.bigdata.common_crawl_ingest import (  # noqa: E402
    run_ingestion,
)
from data_platform.extractors.common_crawl_ingestion import (  # noqa: E402
    CommonCrawlRecoverySnapshotBuilder,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Common Crawl extract→ingest pipeline."
    )
    parser.add_argument(
        "--trigger",
        default="manual",
        choices=["manual", "scheduled"],
        help="Trigger mode written to the Common Crawl ingestion run.",
    )
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        help="Skip archive extraction and only ingest the latest prepared snapshot.",
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Skip DB ingestion and only run archive extraction.",
    )
    parser.add_argument("--max-results-per-query", type=int)
    parser.add_argument("--max-warc-downloads", type=int)
    parser.add_argument("--target-records", type=int)
    parser.add_argument("--async-concurrency", type=int)
    parser.add_argument("--min-text-length", type=int)
    parser.add_argument("--max-text-length", type=int)
    parser.add_argument("--request-timeout", type=int)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument(
        "--query-profile",
        default="default",
        choices=["default", "targeted-smoke", "phishing-refresh"],
        help="Archive query profile to use during extraction.",
    )
    parser.add_argument(
        "--fallback-mode",
        default="none",
        choices=["none", "latest-r2-local", "merge-r2-local"],
        help="Recovery action to take if live Common Crawl extraction fails.",
    )
    parser.add_argument(
        "--recovery-parquet-count",
        type=int,
        default=2,
        help="Number of latest fr_usable R2 parquets to merge during recovery.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    return parser.parse_args()


def _materialize_local_recovery_snapshot(
    *,
    fallback_mode: str,
    recovery_parquet_count: int,
):
    parquet_count = 1 if fallback_mode == "latest-r2-local" else recovery_parquet_count
    builder = CommonCrawlRecoverySnapshotBuilder()
    return builder.materialize_local_snapshot(parquet_count=parquet_count)


async def run_pipeline(
    *,
    trigger_mode: str = "manual",
    skip_extract: bool = False,
    skip_ingest: bool = False,
    extraction_args: argparse.Namespace | None = None,
    query_profile: str | None = None,
    fallback_mode: str | None = None,
    recovery_parquet_count: int | None = None,
) -> dict[str, object]:
    load_dotenv(ROOT_DIR / ".env", override=True)
    if skip_extract and skip_ingest:
        raise ValueError("At least one Common Crawl stage must remain enabled.")

    args = extraction_args or parse_args()
    logging.getLogger().setLevel(args.log_level)
    effective_query_profile = query_profile or args.query_profile
    effective_fallback_mode = fallback_mode or args.fallback_mode
    effective_recovery_parquet_count = (
        args.recovery_parquet_count
        if recovery_parquet_count is None
        else recovery_parquet_count
    )
    if effective_recovery_parquet_count < 1:
        raise ValueError("recovery_parquet_count must be at least 1")

    trace = SemanticTraceLogger(
        parent_type="Orchestration",
        child_target="Common Crawl Pipeline",
        domain="data_platform",
        trace_id=f"common-crawl-pipeline-{uuid.uuid4()}",
    )
    trace.trace(
        stage="orchestration",
        status="start",
        message="Common Crawl pipeline starting",
        metrics={
            "skip_extract": int(skip_extract),
            "skip_ingest": int(skip_ingest),
            "query_profile": effective_query_profile,
            "fallback_mode": effective_fallback_mode,
        },
    )

    payload: dict[str, object] = {
        "trigger_mode": trigger_mode,
        "query_profile": effective_query_profile,
        "skip_extract": skip_extract,
        "skip_ingest": skip_ingest,
        "fallback_mode": effective_fallback_mode,
        "recovery_parquet_count": effective_recovery_parquet_count,
    }

    try:
        if not skip_extract:
            settings = build_settings(args)
            try:
                extraction_result = await run_extraction(
                    settings=settings,
                    query_profile=effective_query_profile,
                )
                payload["extraction"] = {
                    "timestamp": extraction_result.timestamp,
                    "raw_count": extraction_result.raw_count,
                    "usable_french_count": extraction_result.usable_french_count,
                    "raw_storage_uri": extraction_result.artifacts.raw_storage_uri,
                    "fr_usable_storage_uri": extraction_result.artifacts.fr_usable_storage_uri,
                    "quality_report_storage_uri": extraction_result.artifacts.quality_report_storage_uri,
                }
            except Exception as exc:
                payload["extraction_error"] = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
                if effective_fallback_mode == "none":
                    raise

                trace.trace(
                    stage="recovery",
                    status="start",
                    message="Live Common Crawl extraction failed; preparing local recovery snapshot",
                    metrics={
                        "fallback_mode": effective_fallback_mode,
                        "recovery_parquet_count": effective_recovery_parquet_count,
                    },
                )
                recovery_artifact = await asyncio.to_thread(
                    _materialize_local_recovery_snapshot,
                    fallback_mode=effective_fallback_mode,
                    recovery_parquet_count=effective_recovery_parquet_count,
                )
                payload["recovery"] = {
                    "mode": effective_fallback_mode,
                    "row_count": recovery_artifact.row_count,
                    "local_parquet_path": str(
                        recovery_artifact.local_parquet_path.relative_to(ROOT_DIR)
                    ),
                    "manifest_path": str(
                        recovery_artifact.manifest_path.relative_to(ROOT_DIR)
                    ),
                    "selected_object_keys": list(
                        recovery_artifact.selected_object_keys
                    ),
                }
                trace.trace(
                    stage="recovery",
                    status="success",
                    message="Local Common Crawl recovery snapshot prepared",
                    metrics={
                        "recovery_rows": recovery_artifact.row_count,
                        "selected_objects": len(recovery_artifact.selected_object_keys),
                    },
                )

        if not skip_ingest:
            ingestion_result = await run_ingestion(trigger_mode=trigger_mode)
            payload["ingestion"] = {
                "ingestion_run_id": ingestion_result.ingestion_run_id,
                "source_system_id": ingestion_result.source_system_id,
                "raw_object_count": ingestion_result.raw_object_count,
                "raw_record_count": ingestion_result.raw_record_count,
                "skipped_count": ingestion_result.skipped_count,
                "total_extracted_count": ingestion_result.total_extracted_count,
                "snapshot_storage_uri": ingestion_result.snapshot_storage_uri,
                "log_message": ingestion_result.log_message,
            }
    except Exception as exc:
        trace.trace(
            stage="orchestration",
            status="failed",
            message=f"Common Crawl pipeline failed: {exc}",
        )
        raise

    trace.trace(
        stage="orchestration",
        status="success",
        message="Common Crawl pipeline completed",
        metrics={
            "extraction_ran": int(not skip_extract),
            "ingestion_ran": int(not skip_ingest),
            "recovery_used": int("recovery" in payload),
        },
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


async def main() -> None:
    args = parse_args()
    await run_pipeline(
        trigger_mode=args.trigger,
        skip_extract=args.skip_extract,
        skip_ingest=args.skip_ingest,
        extraction_args=args,
    )


if __name__ == "__main__":
    asyncio.run(main())
