"""Manually extract Common Crawl snapshots into the configured snapshot store.

This script is a thin CLI wrapper around
``data_platform.extractors.common_crawl_archive.CommonCrawlArchiveExtractor``.
"""

from __future__ import annotations

import asyncio
import argparse
import logging
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.extractors.common_crawl_archive import (  # noqa: E402
    CommonCrawlArchiveExtractor,
    CommonCrawlArchiveSettings,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract Common Crawl snapshots into the configured snapshot store"
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
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    return parser.parse_args()


def build_settings(args: argparse.Namespace) -> CommonCrawlArchiveSettings:
    overrides = {
        "max_results_per_query": args.max_results_per_query,
        "max_warc_downloads": args.max_warc_downloads,
        "target_records": args.target_records,
        "async_concurrency": args.async_concurrency,
        "min_text_length": args.min_text_length,
        "max_text_length": args.max_text_length,
        "request_timeout": args.request_timeout,
        "batch_size": args.batch_size,
    }
    return CommonCrawlArchiveSettings(
        **{key: value for key, value in overrides.items() if value is not None}
    )


async def main() -> None:
    args = parse_args()
    logging.getLogger().setLevel(args.log_level)
    settings = build_settings(args)
    extractor = CommonCrawlArchiveExtractor(settings=settings)
    result = await extractor.run()

    print(f"Timestamp                 : {result.timestamp}")
    print(f"Raw records               : {result.raw_count:,}")
    print(f"Usable French records     : {result.usable_french_count:,}")
    print(f"Index hits                : {result.stats.total_index_hits:,}")
    print(f"Downloaded WARC responses : {result.stats.total_downloaded:,}")
    print(f"Extracted records         : {result.stats.extracted:,}")
    print(f"Download errors           : {result.stats.download_errors:,}")
    print(f"Skipped short             : {result.stats.skipped_short:,}")
    print(f"Skipped duplicate         : {result.stats.skipped_duplicate:,}")
    print(f"Raw snapshot              : {result.artifacts.raw_storage_uri}")
    if result.artifacts.fr_usable_storage_uri:
        print(f"Usable FR snapshot        : {result.artifacts.fr_usable_storage_uri}")
    print(f"Quality report            : {result.artifacts.quality_report_storage_uri}")


if __name__ == "__main__":
    asyncio.run(main())
