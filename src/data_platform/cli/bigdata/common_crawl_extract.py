from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.trace_logger import SemanticTraceLogger  # noqa: E402
from data_platform.extractors.common_crawl_archive import (  # noqa: E402
    CC_CRAWL_INDICES,
    CommonCrawlArchiveExtractor,
    CommonCrawlArchiveSettings,
    CrawlQuery,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)


TARGETED_SMOKE_QUERIES: tuple[CrawlQuery, ...] = (
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

TARGETED_SMOKE_CRAWL_INDICES: tuple[str, ...] = (
    "CC-MAIN-2025-08",
    "CC-MAIN-2024-51",
    "CC-MAIN-2024-42",
    "CC-MAIN-2024-33",
    "CC-MAIN-2024-22",
    "CC-MAIN-2024-10",
)

PHISHING_REFRESH_QUERIES: tuple[CrawlQuery, ...] = (
    CrawlQuery("signal-arnaques.com/*", "phishing_related", "scam_reports_fr"),
    CrawlQuery(
        "cybermalveillance.gouv.fr/*",
        "phishing_related",
        "cert_gov_fr",
    ),
    CrawlQuery("urlscan.io/result/*", "phishing_related", "url_scanning"),
    CrawlQuery("signal-spam.fr/*", "phishing_related", "signal_spam_fr"),
    CrawlQuery("openphish.com/*", "phishing_related", "phishing_feed"),
    CrawlQuery("abuse.ch/*", "phishing_related", "abuse_ch"),
    CrawlQuery(
        "*.cdiscount.com/newsletter*",
        "spam_like",
        "retail_newsletter_fr",
    ),
)

PHISHING_REFRESH_CRAWL_INDICES: tuple[str, ...] = (
    "CC-MAIN-2025-08",
    "CC-MAIN-2024-51",
    "CC-MAIN-2024-42",
)


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
    parser.add_argument(
        "--query-profile",
        default="default",
        choices=["default", "targeted-smoke", "phishing-refresh"],
        help="Query profile to use during extraction.",
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
    settings = CommonCrawlArchiveSettings()
    for key, value in overrides.items():
        if value is not None:
            setattr(settings, key, value)
    return settings


def resolve_queries(query_profile: str) -> tuple[CrawlQuery, ...] | None:
    if query_profile == "targeted-smoke":
        return TARGETED_SMOKE_QUERIES
    if query_profile == "phishing-refresh":
        return PHISHING_REFRESH_QUERIES
    return None


def resolve_crawl_indices(query_profile: str) -> tuple[str, ...]:
    if query_profile == "targeted-smoke":
        return TARGETED_SMOKE_CRAWL_INDICES
    if query_profile == "phishing-refresh":
        return PHISHING_REFRESH_CRAWL_INDICES
    return CC_CRAWL_INDICES


async def run_extraction(
    *,
    settings: CommonCrawlArchiveSettings,
    query_profile: str = "default",
) -> object:
    trace = SemanticTraceLogger(
        parent_type="Big Data",
        child_target="Common Crawl Archive",
        domain="data_platform",
        trace_id=f"common-crawl-archive-{uuid.uuid4()}",
    )
    trace.trace(
        stage="orchestration",
        status="start",
        message="Common Crawl archive extraction starting",
        metrics={
            "target_records": settings.target_records,
            "max_warc_downloads": settings.max_warc_downloads,
            "max_results_per_query": settings.max_results_per_query,
            "async_concurrency": settings.async_concurrency,
            "query_profile": query_profile,
        },
    )
    extractor = CommonCrawlArchiveExtractor(
        settings=settings,
        queries=resolve_queries(query_profile),
        crawl_indices=resolve_crawl_indices(query_profile),
    )
    try:
        result = await extractor.run()
    except Exception as exc:
        trace.trace(
            stage="orchestration",
            status="failed",
            message=f"Common Crawl archive extraction failed: {exc}",
        )
        raise

    trace.trace(
        stage="extraction",
        status="success",
        message="Common Crawl archive extraction completed",
        metrics={
            "raw_count": result.raw_count,
            "usable_french_count": result.usable_french_count,
            "index_hits": result.stats.total_index_hits,
            "downloaded": result.stats.total_downloaded,
            "download_errors": result.stats.download_errors,
        },
    )
    trace.trace(
        stage="snapshot",
        status="success",
        message="Common Crawl archive snapshots written",
        metrics={
            "has_usable_snapshot": int(bool(result.artifacts.fr_usable_storage_uri)),
        },
    )
    trace.trace(
        stage="orchestration",
        status="success",
        message="Common Crawl archive run complete",
    )
    return result


async def main() -> None:
    args = parse_args()
    logging.getLogger().setLevel(args.log_level)
    settings = build_settings(args)
    result = await run_extraction(
        settings=settings,
        query_profile=args.query_profile,
    )

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
