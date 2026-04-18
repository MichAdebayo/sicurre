from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.extractors.common_crawl_archive import (  # noqa: E402
    CommonCrawlArchiveExtractor,
    CommonCrawlArchiveSettings,
    CrawlQuery,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a bounded targeted Common Crawl local smoke extraction"
    )
    parser.add_argument("--max-results-per-query", type=int, default=80)
    parser.add_argument("--max-warc-downloads", type=int, default=30)
    parser.add_argument("--target-records", type=int, default=18)
    parser.add_argument("--async-concurrency", type=int, default=8)
    parser.add_argument("--request-timeout", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=15)
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    logging.getLogger().setLevel(args.log_level)

    settings = CommonCrawlArchiveSettings()
    settings.max_results_per_query = args.max_results_per_query
    settings.max_warc_downloads = args.max_warc_downloads
    settings.target_records = args.target_records
    settings.async_concurrency = args.async_concurrency
    settings.request_timeout = args.request_timeout
    settings.batch_size = args.batch_size

    queries = (
        CrawlQuery("signal-arnaques.com/*", "phishing_related", "scam_reports_fr"),
        CrawlQuery("zataz.com/*", "phishing_related", "security_news_fr"),
        CrawlQuery(
            "*.cdiscount.com/newsletter*",
            "spam_like",
            "retail_newsletter_fr",
        ),
        CrawlQuery("www.labanquepostale.fr/*", "legitimate", "bank_fr"),
        CrawlQuery("www.lcl.fr/*", "legitimate", "bank_fr"),
    )
    crawl_indices = (
        "CC-MAIN-2025-08",
        "CC-MAIN-2024-51",
        "CC-MAIN-2024-42",
        "CC-MAIN-2024-33",
        "CC-MAIN-2024-22",
        "CC-MAIN-2024-10",
    )

    result = await CommonCrawlArchiveExtractor(
        settings=settings,
        queries=queries,
        crawl_indices=crawl_indices,
    ).run()

    payload = {
        "timestamp": result.timestamp,
        "raw_count": result.raw_count,
        "usable_french_count": result.usable_french_count,
        "raw_storage_uri": result.artifacts.raw_storage_uri,
        "fr_usable_storage_uri": result.artifacts.fr_usable_storage_uri,
        "quality_report_storage_uri": result.artifacts.quality_report_storage_uri,
        "stats": {
            "index_hits": result.stats.total_index_hits,
            "downloaded": result.stats.total_downloaded,
            "extracted": result.stats.extracted,
            "download_errors": result.stats.download_errors,
            "skipped_short": result.stats.skipped_short,
            "skipped_duplicate": result.stats.skipped_duplicate,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())