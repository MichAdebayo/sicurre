"""Manually ingest a merged set of recent Common Crawl snapshots.

This entrypoint is intentionally one-off and should mirror the configured Common
Crawl input surface for the current environment instead of silently bypassing it.
Steady-state cron ingestion should continue selecting only the latest prepared
snapshot.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import sys
from pathlib import Path
from typing import Any

import boto3
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
    CommonCrawlIngestionSettings,
    CommonCrawlBigQueryClient,
    CommonCrawlIngestionService,
    DEFAULT_CC_SNAPSHOT_DIR,
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


class LatestMergedLocalCommonCrawlClient:
    def __init__(
        self,
        *,
        parquet_count: int = 2,
        local_parquet_dir: Path | None = None,
    ) -> None:
        self.parquet_count = parquet_count
        self.local_parquet_dir = (
            local_parquet_dir or DEFAULT_CC_SNAPSHOT_DIR / "fr_usable"
        )
        self.selected_object_keys: list[str] = []
        self.full_table_id = f"local://{self.local_parquet_dir}"

    def fetch_latest_parquet_from_r2(self) -> pd.DataFrame:
        parquet_files = sorted(
            self.local_parquet_dir.glob("*.parquet"),
            key=lambda path: path.stat().st_mtime,
        )
        if len(parquet_files) < self.parquet_count:
            raise FileNotFoundError(
                f"Expected at least {self.parquet_count} parquet files in {self.local_parquet_dir}, found {len(parquet_files)}"
            )

        selected = parquet_files[-self.parquet_count :]
        self.selected_object_keys = [str(path) for path in selected]
        logger.info("Selected local merge inputs: %s", self.selected_object_keys)

        frames = [pd.read_parquet(path, engine="pyarrow") for path in selected]
        merged = pd.concat(frames, ignore_index=True)
        merged = self._deduplicate_frame(merged)
        logger.info(
            "Merged %s local parquet snapshots into %s rows before local deduplication.",
            len(selected),
            len(merged),
        )
        return merged

    def execute_bigquery_pipeline(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        if df.empty:
            return []
        dataframe = df.copy()
        if "content_hash" not in dataframe.columns and "text" in dataframe.columns:
            dataframe["content_hash"] = dataframe["text"].apply(
                lambda text: pd.util.hash_pandas_object(
                    pd.Series([str(text)]), index=False
                )
                .astype(str)
                .iloc[0]
            )
        if "content_hash" in dataframe.columns:
            dataframe = dataframe.drop_duplicates(subset=["content_hash"])
        elif "text" in dataframe.columns:
            dataframe = dataframe.drop_duplicates(subset=["text"])

        if "text_length" in dataframe.columns:
            dataframe = dataframe[dataframe["text_length"].between(100, 10000)]
        elif "text" in dataframe.columns:
            dataframe = dataframe[dataframe["text"].str.len().between(100, 10000)]

        logger.info(
            "LatestMergedLocalCommonCrawlClient: %d deduplicated records after pandas pipeline",
            len(dataframe),
        )
        return dataframe.to_dict(orient="records")

    @staticmethod
    def _deduplicate_frame(dataframe: pd.DataFrame) -> pd.DataFrame:
        if dataframe.empty:
            return dataframe
        if "content_hash" in dataframe.columns:
            return dataframe.drop_duplicates(subset=["content_hash"]).reset_index(
                drop=True
            )
        if "text" in dataframe.columns:
            return dataframe.drop_duplicates(subset=["text"]).reset_index(drop=True)
        return dataframe.drop_duplicates().reset_index(drop=True)


class ExplicitSnapshotCommonCrawlClient:
    def __init__(self, *, snapshot_keys: list[str]) -> None:
        if not snapshot_keys:
            raise ValueError("snapshot_keys must not be empty")

        settings = CommonCrawlIngestionSettings.from_app_settings()
        if not all(
            [
                settings.raw_snapshot_r2_endpoint_url,
                settings.raw_snapshot_r2_access_key_id,
                settings.raw_snapshot_r2_secret_access_key,
            ]
        ):
            raise RuntimeError(
                "Missing Common Crawl R2 credentials for explicit snapshot replay."
            )

        self.snapshot_keys = snapshot_keys
        self.selected_object_keys = list(snapshot_keys)
        self.r2_bucket = settings.raw_snapshot_r2_bucket_name
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.raw_snapshot_r2_endpoint_url,
            aws_access_key_id=settings.raw_snapshot_r2_access_key_id,
            aws_secret_access_key=settings.raw_snapshot_r2_secret_access_key,
            region_name=settings.raw_snapshot_r2_region,
        )
        joined_keys = ",".join(snapshot_keys)
        self.full_table_id = f"explicit-r2-snapshot://{self.r2_bucket}/{joined_keys}"

    def fetch_latest_parquet_from_r2(self) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for key in self.snapshot_keys:
            payload = json.loads(
                self.s3_client.get_object(Bucket=self.r2_bucket, Key=key)["Body"].read()
            )
            records = payload.get("records") or []
            frames.append(pd.DataFrame.from_records(records))

        merged = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        logger.info(
            "Loaded %s explicit snapshot payloads into %s rows before deduplication.",
            len(self.snapshot_keys),
            len(merged),
        )
        return merged

    def execute_bigquery_pipeline(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        dataframe = LatestMergedLocalCommonCrawlClient._deduplicate_frame(df.copy())
        if dataframe.empty:
            return []
        if "text_length" in dataframe.columns:
            dataframe = dataframe[dataframe["text_length"].between(100, 10000)]
        elif "text" in dataframe.columns:
            dataframe = dataframe[dataframe["text"].str.len().between(100, 10000)]

        logger.info(
            "ExplicitSnapshotCommonCrawlClient: %d deduplicated records after replay pipeline",
            len(dataframe),
        )
        return dataframe.to_dict(orient="records")


class ExplicitParquetCommonCrawlClient:
    def __init__(self, *, parquet_keys: list[str]) -> None:
        if not parquet_keys:
            raise ValueError("parquet_keys must not be empty")

        settings = CommonCrawlIngestionSettings.from_app_settings()
        if not all(
            [
                settings.raw_snapshot_r2_endpoint_url,
                settings.raw_snapshot_r2_access_key_id,
                settings.raw_snapshot_r2_secret_access_key,
            ]
        ):
            raise RuntimeError(
                "Missing Common Crawl R2 credentials for explicit parquet replay."
            )

        self.parquet_keys = parquet_keys
        self.selected_object_keys = list(parquet_keys)
        self.r2_bucket = settings.raw_snapshot_r2_bucket_name
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.raw_snapshot_r2_endpoint_url,
            aws_access_key_id=settings.raw_snapshot_r2_access_key_id,
            aws_secret_access_key=settings.raw_snapshot_r2_secret_access_key,
            region_name=settings.raw_snapshot_r2_region,
        )
        joined_keys = ",".join(parquet_keys)
        self.full_table_id = f"explicit-r2-parquet://{self.r2_bucket}/{joined_keys}"

    def fetch_latest_parquet_from_r2(self) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for key in self.parquet_keys:
            buf = io.BytesIO()
            self.s3_client.download_fileobj(self.r2_bucket, key, buf)
            buf.seek(0)
            frames.append(pd.read_parquet(buf, engine="pyarrow"))

        merged = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        logger.info(
            "Loaded %s explicit parquet payloads into %s rows before deduplication.",
            len(self.parquet_keys),
            len(merged),
        )
        return merged

    def execute_bigquery_pipeline(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        dataframe = LatestMergedLocalCommonCrawlClient._deduplicate_frame(df.copy())
        if dataframe.empty:
            return []
        if "text_length" in dataframe.columns:
            dataframe = dataframe[dataframe["text_length"].between(100, 10000)]
        elif "text" in dataframe.columns:
            dataframe = dataframe[dataframe["text"].str.len().between(100, 10000)]

        logger.info(
            "ExplicitParquetCommonCrawlClient: %d deduplicated records after replay pipeline",
            len(dataframe),
        )
        return dataframe.to_dict(orient="records")


def _build_merge_client(
    *,
    parquet_count: int,
    input_backend: str,
    parquet_keys: list[str] | None = None,
    snapshot_keys: list[str] | None = None,
):
    if parquet_keys:
        return ExplicitParquetCommonCrawlClient(parquet_keys=parquet_keys)

    if snapshot_keys:
        return ExplicitSnapshotCommonCrawlClient(snapshot_keys=snapshot_keys)

    normalized_backend = input_backend.strip().lower()
    if normalized_backend == "local":
        return LatestMergedLocalCommonCrawlClient(parquet_count=parquet_count)
    if normalized_backend == "prod":
        return LatestMergedCommonCrawlBigQueryClient(parquet_count=parquet_count)
    raise ValueError(
        f"Unsupported Common Crawl input backend for merged ingest: {input_backend}"
    )


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manually ingest a merged set of the latest Common Crawl fr_usable parquet files from the configured input backend."
    )
    parser.add_argument(
        "--parquet-count",
        type=int,
        default=2,
        help="Number of latest fr_usable parquet snapshots to merge for this one-time ingestion.",
    )
    parser.add_argument(
        "--input-backend",
        choices=["auto", "local", "prod"],
        default="auto",
        help="Which Common Crawl input backend to merge from. 'auto' follows CC_INPUT_BACKEND from settings.",
    )
    parser.add_argument(
        "--parquet-key",
        action="append",
        default=[],
        help="Exact R2 Common Crawl fr_usable parquet object key to replay. Repeat the flag to provide multiple keys. When set, latest-parquet selection is bypassed.",
    )
    parser.add_argument(
        "--snapshot-key",
        action="append",
        default=[],
        help="Exact R2 Common Crawl raw snapshot JSON object key to replay. Repeat the flag to provide multiple keys. When set, latest-parquet selection is bypassed.",
    )
    args = parser.parse_args()

    if args.parquet_key and args.snapshot_key:
        raise ValueError("Use either --parquet-key or --snapshot-key, not both.")

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    configured_input_backend = settings.cc_input_backend
    effective_input_backend = (
        configured_input_backend if args.input_backend == "auto" else args.input_backend
    )
    effective_client_mode = effective_input_backend
    if args.parquet_key:
        effective_client_mode = "explicit-r2-parquet"
    elif args.snapshot_key:
        effective_client_mode = "explicit-r2-snapshot"
    logger.info(
        "Merged Common Crawl ingest using client mode=%s (configured backend=%s)",
        effective_client_mode,
        configured_input_backend,
    )

    client = _build_merge_client(
        parquet_count=args.parquet_count,
        input_backend=effective_input_backend,
        parquet_keys=args.parquet_key,
        snapshot_keys=args.snapshot_key,
    )
    service = CommonCrawlIngestionService(bq_client=client)

    async with session_factory() as session:
        result = await service.run(session, trigger_mode="manual_merge")

    print("=====================================================")
    print(result.log_message or "Merged Common Crawl ingestion completed")
    print("=====================================================")
    print(f"  Input backend:          {effective_client_mode}")
    print(f"  Selected inputs:        {len(client.selected_object_keys)}")
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
