"""Run the scheduled Common Crawl big-data pipeline delegate."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.cli.bigdata.common_crawl_pipeline import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the scheduled Common Crawl extract→ingest delegate."
    )
    return parser.parse_args()


def build_scheduled_args() -> argparse.Namespace:
    return argparse.Namespace(
        trigger="scheduled",
        skip_extract=False,
        skip_ingest=False,
        max_results_per_query=80,
        max_warc_downloads=80,
        target_records=50,
        async_concurrency=6,
        min_text_length=None,
        max_text_length=None,
        request_timeout=15,
        batch_size=20,
        query_profile="phishing-refresh",
        fallback_mode="merge-r2-local",
        recovery_parquet_count=2,
        log_level="INFO",
    )


if __name__ == "__main__":
    parse_args()
    asyncio.run(
        run_pipeline(
            trigger_mode="scheduled",
            extraction_args=build_scheduled_args(),
            query_profile="phishing-refresh",
            fallback_mode="merge-r2-local",
            recovery_parquet_count=2,
        )
    )
