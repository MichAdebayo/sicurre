"""Run a one-time Common Crawl ingestion over the latest two R2 fr_usable parquet snapshots.

This script is intentionally transient and does not change the default extractor behavior,
which should continue selecting only the latest parquet for steady-state cron ingestion.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import get_settings
from core.database import Base
from data_platform.extractors.common_crawl_ingestion import (
    CommonCrawlBigQueryClient,
    CommonCrawlIngestionService,
)


FR_USABLE_PREFIX = "raw-snapshots/bigdata/common_crawl/fr_usable/"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


class LatestMergedCommonCrawlBigQueryClient(CommonCrawlBigQueryClient):
    def __init__(self, parquet_count: int = 2) -> None:
        super().__init__()
        self.parquet_count = parquet_count
        self.selected_object_keys: list[str] = []

    def fetch_latest_parquet_from_r2(self) -> pd.DataFrame:
        response = self.s3_client.list_objects_v2(
            Bucket=self.r2_bucket,
            Prefix=FR_USABLE_PREFIX,
        )
        objects = [
            obj
            for obj in response.get("Contents", [])
            if obj["Key"].endswith(".parquet")
        ]
        if len(objects) < self.parquet_count:
            raise FileNotFoundError(
                f"Expected at least {self.parquet_count} parquet files in r2://{self.r2_bucket}/{FR_USABLE_PREFIX}, found {len(objects)}"
            )

        selected = sorted(
            objects,
            key=lambda item: item["LastModified"],
            reverse=True,
        )[: self.parquet_count]
        self.selected_object_keys = [obj["Key"] for obj in selected]
        logger.info("Selected merge inputs: %s", self.selected_object_keys)

        frames: list[pd.DataFrame] = []
        for obj in selected:
            buf = io.BytesIO()
            self.s3_client.download_fileobj(self.r2_bucket, obj["Key"], buf)
            buf.seek(0)
            frames.append(pd.read_parquet(buf, engine="pyarrow"))

        merged = pd.concat(frames, ignore_index=True)
        logger.info(
            "Merged %s parquet snapshots into %s rows before BigQuery deduplication.",
            len(selected),
            len(merged),
        )
        return merged


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a one-time merged Common Crawl ingestion using the latest two R2 fr_usable parquet files."
    )
    parser.add_argument(
        "--parquet-count",
        type=int,
        default=2,
        help="Number of latest fr_usable parquet snapshots to merge for this one-time ingestion.",
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    client = LatestMergedCommonCrawlBigQueryClient(parquet_count=args.parquet_count)
    service = CommonCrawlIngestionService(bq_client=client)

    async with session_factory() as session:
        result = await service.run(session, trigger_mode="manual_merge")

    print("=====================================================")
    print(result.log_message or "Merged Common Crawl ingestion completed")
    print("=====================================================")
    print(f"  Selected parquet inputs: {len(client.selected_object_keys)}")
    for key in client.selected_object_keys:
        print(f"    - {key}")
    print(
        f"  Total Processed BigQuery: {result.total_extracted_count}\n"
        f"  New Records Saved:      {result.raw_record_count}\n"
        f"  Skipped (Existing):     {result.skipped_count}\n"
        f"  Snapshot Extracted:     {result.raw_object_count}"
    )
    if result.snapshot_storage_uri:
        print(f"  Snapshot URI:           {result.snapshot_storage_uri}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
