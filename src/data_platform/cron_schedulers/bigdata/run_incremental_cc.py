"""Run the resumable, time-bounded Common Crawl cron pipeline.

Forces R2 storage under cron/bigdata/common_crawl/ prefix.
Pass --reserved to write under cron/reserved/bigdata/common_crawl/ instead.
Duration is controlled by SICURRE_CC_CRON_DURATION_MODE:
  - 'short'    → 30 minutes (for demos / jury)
  - 'standard' → 8 hours    (for overnight runs)
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse as _argparse
import asyncio
import io
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

# ── Reserved-slot routing (must happen before settings are loaded) ─────────────
_parser = _argparse.ArgumentParser(add_help=False)
_parser.add_argument("--reserved", action="store_true", default=False)
_reserved_args, _ = _parser.parse_known_args()

# Force snapshot storage to R2 under the appropriate cron prefix
os.environ["SICURRE_COMMON_CRAWL_SNAPSHOT_STORAGE_BACKEND"] = "prod"
os.environ["SICURRE_COMMON_CRAWL_SNAPSHOT_PREFIX"] = (
    "cron/reserved/bigdata/common_crawl" if _reserved_args.reserved else "cron/bigdata/common_crawl"
)
# ──────────────────────────────────────────────────────────────────────────────

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import get_settings
from core.database import Base
from data_platform.extractors.common_crawl_ingestion import (
    CommonCrawlIngestionResult,
    CommonCrawlIngestionService,
    LocalCommonCrawlClient,
)
from data_platform.extractors.incremental_cc_extractor import (
    DURATION_MAP,
    IncrementalCommonCrawlExtractor,
)
from data_platform.services.shared.r2_read_client import R2ReadClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


class R2CronSnapshotCommonCrawlClient(LocalCommonCrawlClient):
    """Read a scheduled Common Crawl snapshot from R2 for DB ingestion."""

    def __init__(self, *, snapshot_key: str) -> None:
        """Bind the read client to one R2 snapshot object."""
        super().__init__()
        self.snapshot_key = snapshot_key
        self.r2 = R2ReadClient()
        self.full_table_id = f"r2://{self.r2.bucket}/{snapshot_key}"

    def fetch_latest_parquet_from_r2(self) -> pd.DataFrame:
        """Download the configured R2 parquet snapshot into a data frame."""
        logger.info(
            "R2CronSnapshotCommonCrawlClient: reading r2://%s/%s",
            self.r2.bucket,
            self.snapshot_key,
        )
        data = self.r2.download_bytes(self.snapshot_key)
        return pd.read_parquet(io.BytesIO(data), engine="pyarrow")


async def _ingest_snapshot_keys(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    snapshot_keys: Sequence[str],
) -> list[CommonCrawlIngestionResult]:
    """Ingest newly flushed scheduled R2 snapshots into the data platform."""
    results: list[CommonCrawlIngestionResult] = []
    for snapshot_key in snapshot_keys:
        service = CommonCrawlIngestionService(
            bq_client=R2CronSnapshotCommonCrawlClient(snapshot_key=snapshot_key)
        )
        async with session_factory() as session:
            result = await service.run(session, trigger_mode="scheduled")
        results.append(result)
    return results


async def run_incremental_cc_cron() -> None:
    """Run one bounded Common Crawl extraction and ingest its snapshots."""
    settings = get_settings()
    duration_mode = settings.cc_cron_duration_mode.strip().lower()
    max_runtime = DURATION_MAP.get(duration_mode)

    if max_runtime is None:
        logger.error(
            "Invalid CC_CRON_DURATION_MODE: '%s'. Must be 'short' or 'standard'.",
            duration_mode,
        )
        raise SystemExit(1)

    logger.info(
        "CC Cron duration mode: %s (%d minutes)",
        duration_mode,
        max_runtime // 60,
    )

    engine = create_async_engine(settings.data_platform_database_url, echo=False)

    # Ensure the pipeline_state table exists
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    extractor = IncrementalCommonCrawlExtractor(
        max_runtime_seconds=max_runtime,
        lookback_indices=settings.cc_cron_lookback_indices,
        max_index_attempts=settings.cc_cron_index_max_attempts,
        index_retry_backoff_seconds=settings.cc_cron_index_retry_backoff_seconds,
        max_results_per_query=settings.cc_max_results_per_query,
        max_warc_downloads_per_index=settings.cc_max_warc_downloads,
        async_concurrency=settings.cc_async_concurrency,
        min_text_length=settings.cc_min_text_length,
        max_text_length=settings.cc_max_text_length,
        request_timeout=settings.cc_request_timeout,
        warc_max_retries=settings.cc_warc_max_retries,
        warc_retry_delay_seconds=settings.cc_warc_retry_delay_seconds,
    )

    ingestion_results: list[CommonCrawlIngestionResult] = []
    async with session_factory() as session:
        result = await extractor.run(session)

    if result.r2_uris:
        ingestion_results = await _ingest_snapshot_keys(
            session_factory,
            snapshot_keys=result.r2_uris,
        )

    logger.info("--- CC Cron Summary ---")
    logger.info("Indices attempted: %s", result.indices_attempted)
    logger.info("Indices completed: %s", result.indices_completed)
    logger.info("Indices failed:    %s", result.indices_failed)
    logger.info("Total extracted:   %d", result.total_extracted)
    logger.info("Timed out:         %s", result.timed_out)
    logger.info("R2 URIs:           %s", result.r2_uris)
    logger.info("Ingested snapshots: %d", len(ingestion_results))
    logger.info(
        "Ingested raw records: %d",
        sum(item.raw_record_count for item in ingestion_results),
    )

    await engine.dispose()


async def main() -> None:
    """Launch the scheduled Common Crawl job after logging its R2 target."""
    _r2_prefix = os.environ["SICURRE_COMMON_CRAWL_SNAPSHOT_PREFIX"]
    logger.info("Starting Common Crawl cron (R2 target: %s)", _r2_prefix)
    await run_incremental_cc_cron()


if __name__ == "__main__":
    asyncio.run(main())
