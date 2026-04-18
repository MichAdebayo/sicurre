"""Ingest prepared Common Crawl parquet snapshots into the Sicurre DB."""

from __future__ import annotations

import io
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import hashlib
import pandas as pd
from google.cloud import bigquery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import ROOT_DIR, Settings, get_settings
from core.trace_logger import SemanticTraceLogger
from data_platform.api.schemas import DataSourceCreate, IngestionRunCreate
from data_platform.services.shared.snapshot_storage import (
    SnapshotStore,
    SnapshotWriteResult,
    build_snapshot_store,
)
from db.models import (
    DataIngestionRun,
    DataRawObject,
    DataRawRecord,
    DataSourceSystem,
    IngestionStatus,
    ObjectType,
    SourceType,
)
from db.queries import SourceSystemQueries
from db.services.lineage import IngestionRunService, SourceSystemService

logger = logging.getLogger(__name__)

REPO_ROOT = ROOT_DIR
DEFAULT_CC_SOURCE_NAME = "common-crawl-bigdata"
DEFAULT_CC_SNAPSHOT_DIR = REPO_ROOT / "data" / "raw" / "bigdata" / "common_crawl"
DEFAULT_CC_SNAPSHOT_PREFIX = "common_crawl"


@dataclass(frozen=True, slots=True)
class CommonCrawlIngestionSettings:
    gcp_project: str = "sicurre"
    gcp_region: str = "europe-west1"
    dataset_id: str = "sicurre_dataset"
    raw_snapshot_r2_bucket_name: str = "sicurre-raw"
    raw_snapshot_r2_endpoint_url: str | None = None
    raw_snapshot_r2_access_key_id: str | None = None
    raw_snapshot_r2_secret_access_key: str | None = None
    raw_snapshot_r2_region: str = "auto"

    @classmethod
    def from_app_settings(
        cls,
        app_settings: Settings | None = None,
    ) -> CommonCrawlIngestionSettings:
        settings = app_settings or get_settings()
        return cls(
            gcp_project=settings.gcp_project,
            gcp_region=settings.gcp_region,
            dataset_id=settings.bigquery_dataset_id,
            raw_snapshot_r2_bucket_name=settings.raw_snapshot_r2_bucket_name
            or cls.raw_snapshot_r2_bucket_name,
            raw_snapshot_r2_endpoint_url=settings.raw_snapshot_r2_endpoint_url,
            raw_snapshot_r2_access_key_id=settings.raw_snapshot_r2_access_key_id,
            raw_snapshot_r2_secret_access_key=settings.raw_snapshot_r2_secret_access_key,
            raw_snapshot_r2_region=settings.raw_snapshot_r2_region,
        )


@dataclass(slots=True)
class CommonCrawlIngestionResult:
    ingestion_run_id: str
    source_system_id: str
    snapshot_path: Path | None
    snapshot_storage_uri: str
    raw_object_count: int
    raw_record_count: int
    skipped_count: int
    total_extracted_count: int
    log_message: str


# ---------------------------------------------------------------------------
# Local (no-cloud) client — used when CC_INPUT_BACKEND=local
# ---------------------------------------------------------------------------


class LocalCommonCrawlClient:
    """Pandas-only Common Crawl client for local/cron mode.

    Reads the most recent ``.parquet`` file from a local directory and
    performs in-process deduplication via SHA-256 text fingerprints,
    replacing the R2 + BigQuery pipeline used in production.
    """

    def __init__(
        self,
        *,
        local_parquet_dir: Path | None = None,
        settings: Settings | None = None,
    ) -> None:
        _settings = settings or get_settings()
        self.local_parquet_dir: Path = local_parquet_dir or (
            _settings.raw_snapshot_local_dir / "bigdata" / "common_crawl" / "fr_usable"
        )
        # Mirrors the attribute used in _build_raw_object external_ref
        self.full_table_id = f"local://{self.local_parquet_dir}"

    def fetch_latest_parquet_from_r2(self) -> pd.DataFrame:
        """Read the most recently modified ``.parquet`` in the local cron dir."""
        parquet_files = sorted(
            self.local_parquet_dir.glob("*.parquet"),
            key=lambda p: p.stat().st_mtime,
        )
        if not parquet_files:
            raise FileNotFoundError(
                f"No .parquet files found in {self.local_parquet_dir}"
            )
        latest = parquet_files[-1]
        logger.info("LocalCommonCrawlClient: reading %s", latest)
        df = pd.read_parquet(latest)
        logger.info("Parsed DataFrame with %d rows.", len(df))
        return df

    def execute_bigquery_pipeline(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Pandas dedup equivalent of the BigQuery FARM_FINGERPRINT pipeline."""
        if df.empty:
            return []
        if "text" not in df.columns:
            logger.warning(
                "LocalCommonCrawlClient: DataFrame has no 'text' column — 0 records"
            )
            return []

        # Deterministic fingerprint: sha256 hex of text (same text = same key across runs)
        df = df.copy()
        df["record_key"] = df["text"].apply(
            lambda t: hashlib.sha256(str(t).encode("utf-8")).hexdigest()
        )

        # Dedup within this batch (keep first occurrence)
        df = df.drop_duplicates(subset=["record_key"])

        # Apply same text length filter as BigQuery pipeline
        if "text_length" in df.columns:
            df = df[df["text_length"].between(100, 10000)]
        elif "text" in df.columns:
            df = df[df["text"].str.len().between(100, 10000)]

        logger.info(
            "LocalCommonCrawlClient: %d deduplicated records after pandas pipeline",
            len(df),
        )
        return df.to_dict(orient="records")


# ---------------------------------------------------------------------------
# Production BigQuery client
# ---------------------------------------------------------------------------


class CommonCrawlBigQueryClient:
    """Handles fetching Parquet from Cloudflare R2 and processing it in Google BigQuery."""

    def __init__(
        self,
        settings: CommonCrawlIngestionSettings | None = None,
    ) -> None:
        self.settings = settings or CommonCrawlIngestionSettings.from_app_settings()
        self.bq_client = bigquery.Client()
        self.project_id = self.settings.gcp_project
        self.dataset_id = self.settings.dataset_id
        self.table_name = "common_crawl_raw"
        self.full_table_id = f"{self.project_id}.{self.dataset_id}.{self.table_name}"

        self.r2_bucket = self.settings.raw_snapshot_r2_bucket_name
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=self.settings.raw_snapshot_r2_endpoint_url,
            aws_access_key_id=self.settings.raw_snapshot_r2_access_key_id,
            aws_secret_access_key=self.settings.raw_snapshot_r2_secret_access_key,
            region_name=self.settings.raw_snapshot_r2_region,
        )

    def fetch_latest_parquet_from_r2(self) -> pd.DataFrame:
        """Finds the most recently created fr_usable parquet file in R2 and downloads it into Pandas."""
        logger.info(
            f"Searching R2 bucket '{self.r2_bucket}' for latest Common Crawl parquet..."
        )
        prefix = "raw-snapshots/bigdata/common_crawl/fr_usable/"

        response = self.s3_client.list_objects_v2(Bucket=self.r2_bucket, Prefix=prefix)
        if "Contents" not in response:
            raise FileNotFoundError(
                f"No objects found in r2://{self.r2_bucket}/{prefix}"
            )

        # Find the most recent .parquet file
        objects = [
            obj for obj in response["Contents"] if obj["Key"].endswith(".parquet")
        ]
        if not objects:
            raise FileNotFoundError(
                f"No .parquet files found in r2://{self.r2_bucket}/{prefix}"
            )

        latest_obj = max(objects, key=lambda x: x["LastModified"])
        object_key = latest_obj["Key"]
        logger.info(f"Found latest parquet: r2://{self.r2_bucket}/{object_key}")

        # Download to memory buffer
        buf = io.BytesIO()
        self.s3_client.download_fileobj(self.r2_bucket, object_key, buf)
        buf.seek(0)

        logger.info("Parsing Parquet with PyArrow...")
        df = pd.read_parquet(buf)
        logger.info(f"Parsed DataFrame with {len(df)} rows.")
        return df

    def execute_bigquery_pipeline(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Loads data to BigQuery, deduplicates using FARM_FINGERPRINT, and extracts the results."""
        logger.info(f"Ensuring internal dataset {self.dataset_id} exists...")
        dataset_ref = bigquery.Dataset(f"{self.project_id}.{self.dataset_id}")
        dataset_ref.location = self.settings.gcp_region
        self.bq_client.create_dataset(dataset_ref, exists_ok=True)

        logger.info(
            f"Pushing {len(df)} rows to BigQuery native table: {self.full_table_id}"
        )
        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
        )
        load_job = self.bq_client.load_table_from_dataframe(
            dataframe=df,
            destination=self.full_table_id,
            job_config=job_config,
        )
        load_job.result()  # Wait for upload completion

        logger.info("Executing analytical Big Data SQL Deduplication Query...")
        query_label_select = (
            "\n            query_label," if "query_label" in df.columns else ""
        )
        # Big SQL Query demonstrating competency C1
        sql = f"""
        SELECT
            CAST(FARM_FINGERPRINT(text) AS STRING) AS record_key,
            url,
            text,
            language,
            category,
            label,
            {query_label_select}
            query,
            crawl_id,
            content_hash
        FROM `{self.full_table_id}`
        WHERE text_length BETWEEN 100 AND 10000
        -- Deduplicate keeping the longest textual representation of identical content
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY FARM_FINGERPRINT(text)
            ORDER BY text_length DESC
        ) = 1
        """

        query_job = self.bq_client.query(sql)
        results_df = query_job.to_dataframe()

        logger.info(
            f"BigQuery aggregation generated {len(results_df)} pristine deduplicated records."
        )
        # Convert DataFrame rows into a list of dicts for the ingestion service
        return results_df.to_dict(orient="records")


# ---------------------------------------------------------------------------
# Factory — select client based on CC_INPUT_BACKEND env var
# ---------------------------------------------------------------------------


def _build_cc_client(
    settings: Settings | None = None,
) -> CommonCrawlBigQueryClient | LocalCommonCrawlClient:
    """Return the correct CC client based on ``CC_INPUT_BACKEND``."""
    _settings = settings or get_settings()
    if _settings.cc_input_backend.lower() == "local":
        return LocalCommonCrawlClient(settings=_settings)
    return CommonCrawlBigQueryClient(
        settings=CommonCrawlIngestionSettings.from_app_settings(_settings)
    )


class CommonCrawlIngestionService:
    def __init__(
        self,
        *,
        bq_client: "CommonCrawlBigQueryClient | LocalCommonCrawlClient | None" = None,
        snapshot_dir: Path = DEFAULT_CC_SNAPSHOT_DIR,
        snapshot_store: SnapshotStore | None = None,
        snapshot_prefix: str = DEFAULT_CC_SNAPSHOT_PREFIX,
        source_name: str = DEFAULT_CC_SOURCE_NAME,
    ) -> None:
        self.bq_client = bq_client or _build_cc_client()
        self.snapshot_dir = snapshot_dir
        self.snapshot_prefix = snapshot_prefix

        local_snapshot_root = (
            snapshot_dir.parent
            if snapshot_dir.name == snapshot_prefix
            else snapshot_dir
        )
        self.snapshot_store = snapshot_store or build_snapshot_store(
            local_root_dir=local_snapshot_root,
            repo_root=REPO_ROOT,
            source_key="common_crawl",
        )

        self.source_name = source_name
        self.source_service = SourceSystemService()
        self.ingestion_service = IngestionRunService()
        self.source_repository = SourceSystemQueries()
        self.trace = SemanticTraceLogger(
            parent_type="Big Data",
            child_target="Common Crawl",
            domain="data_platform",
        )

    async def run(
        self,
        session: AsyncSession,
        *,
        trigger_mode: str = "manual",
        started_at: datetime | None = None,
    ) -> CommonCrawlIngestionResult:
        run_started_at = started_at or datetime.now(timezone.utc)
        self.trace.trace(
            stage="orchestration",
            status="start",
            message="Common Crawl ingestion starting",
        )
        source_system = await self._get_or_create_source_system(session)
        ingestion_run = await self.ingestion_service.create(
            session,
            IngestionRunCreate(
                source_system_id=source_system.id,
                started_at=run_started_at,
                status=IngestionStatus.RUNNING,
                trigger_mode=trigger_mode,
                log_message="Common Crawl BigQuery processing started",
            ),
        )
        self.trace.set_trace_id(str(ingestion_run.id))

        try:
            # 1. Pipeline: R2 -> Pandas -> BigQuery -> Pandas
            # Because bq_client methods are synchronous (boto3, bigquery), we wrap them in a sync def
            # but we can await them by running in a threadpool to remain async-friendly if needed.
            # For simplicity, we just execute them directly since this is a heavy background task.
            self.trace.trace(
                stage="extraction",
                status="start",
                message="Starting R2 → BigQuery pipeline",
            )
            df_parquet = self.bq_client.fetch_latest_parquet_from_r2()
            entries = self.bq_client.execute_bigquery_pipeline(df_parquet)
            total_extracted_count = len(entries)
            self.trace.trace(
                stage="extraction",
                status="success",
                message=f"Pipeline yielded {total_extracted_count} entries",
                metrics={"total_extracted": total_extracted_count},
            )

            if not entries:
                ingestion_run.finished_at = datetime.now(timezone.utc)
                ingestion_run.status = IngestionStatus.COMPLETED
                ingestion_run.log_message = "BigQuery pipeline returned 0 entries"
                self.trace.trace(
                    stage="orchestration",
                    status="success",
                    message="Common Crawl run complete — nothing extracted",
                )
                await session.commit()
                return self._empty_result(ingestion_run, source_system)

            # 2. Dedup against Sicurre DB
            existing_keys = await self._existing_record_keys(session)
            new_entries = [
                e for e in entries if self._entry_key(e) not in existing_keys
            ]
            skipped_count = len(entries) - len(new_entries)

            if not new_entries:
                ingestion_run.finished_at = datetime.now(timezone.utc)
                ingestion_run.status = IngestionStatus.COMPLETED
                ingestion_run.log_message = (
                    f"All {len(entries)} Common Crawl entries already processed."
                )
                self.trace.trace(
                    stage="ingestion",
                    status="skipped",
                    message=f"All {len(entries)} entries already in DB — delta is zero",
                    metrics={"skipped": skipped_count},
                )
                self.trace.trace(
                    stage="orchestration",
                    status="success",
                    message="Common Crawl run complete — no delta",
                )
                await session.commit()
                return self._empty_result(
                    ingestion_run,
                    source_system,
                    skipped_count=skipped_count,
                    total_extracted_count=total_extracted_count,
                )

            # 3. Snapshot logic
            snapshot_payload = {
                "source": "Common Crawl BigQuery Transformation",
                "extracted_at": run_started_at.isoformat(),
                "records": new_entries,
            }
            snapshot_result = await self._write_snapshot(
                ingestion_run=ingestion_run,
                payload=snapshot_payload,
            )
            self.trace.trace(
                stage="snapshot",
                status="success",
                message=f"Snapshot written: {snapshot_result.storage_uri}",
            )

            # 4. DB Entity Creation
            raw_object = self._build_raw_object(
                ingestion_run=ingestion_run,
                source_system=source_system,
                snapshot_result=snapshot_result,
                collected_at=run_started_at,
                entry_count=len(new_entries),
            )
            session.add(raw_object)
            await session.flush()

            raw_records = self._build_raw_records(
                raw_object=raw_object, entries=new_entries, source_system=source_system
            )
            session.add_all(raw_records)

            log_message = f"Common Crawl ingestion completed: {len(raw_records)} new entries, {skipped_count} skipped."
            ingestion_run.finished_at = datetime.now(timezone.utc)
            ingestion_run.status = IngestionStatus.COMPLETED
            ingestion_run.raw_object_count = 1
            ingestion_run.raw_record_count = len(raw_records)
            ingestion_run.log_message = log_message
            self.trace.trace(
                stage="ingestion",
                status="success",
                message=f"Common Crawl ingestion completed: {len(raw_records)} new records",
                metrics={
                    "new_records": len(raw_records),
                    "skipped": skipped_count,
                    "total_extracted": total_extracted_count,
                },
            )
            self.trace.trace(
                stage="orchestration",
                status="success",
                message="Common Crawl run complete",
            )
            await session.commit()

            return CommonCrawlIngestionResult(
                ingestion_run_id=str(ingestion_run.id),
                source_system_id=str(source_system.id),
                snapshot_path=snapshot_result.local_path,
                snapshot_storage_uri=snapshot_result.storage_uri,
                raw_object_count=1,
                raw_record_count=len(raw_records),
                skipped_count=skipped_count,
                total_extracted_count=total_extracted_count,
                log_message=log_message,
            )

        except Exception as exc:
            ingestion_run.finished_at = datetime.now(timezone.utc)
            ingestion_run.status = IngestionStatus.FAILED
            ingestion_run.log_message = f"Common Crawl ingestion failed: {exc}"
            self.trace.trace(
                stage="orchestration",
                status="failed",
                message=f"Common Crawl ingestion failed: {exc}",
            )
            await session.commit()
            raise

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _empty_result(
        self,
        run: DataIngestionRun,
        source: DataSourceSystem,
        *,
        skipped_count: int = 0,
        total_extracted_count: int = 0,
    ) -> CommonCrawlIngestionResult:
        return CommonCrawlIngestionResult(
            ingestion_run_id=str(run.id),
            source_system_id=str(source.id),
            snapshot_path=None,
            snapshot_storage_uri="",
            raw_object_count=0,
            raw_record_count=0,
            skipped_count=skipped_count,
            total_extracted_count=total_extracted_count,
            log_message=run.log_message or "",
        )

    async def _existing_record_keys(
        self,
        session: AsyncSession,
    ) -> set[str]:
        stmt = (
            select(DataRawRecord.record_key, DataRawRecord.raw_content)
            .join(DataRawObject)
            .join(DataIngestionRun)
            .join(DataSourceSystem)
            .where(DataSourceSystem.name == self.source_name)
        )
        rows = await session.execute(stmt)
        existing_keys: set[str] = set()

        for record_key, raw_content in rows:
            if record_key:
                existing_keys.add(str(record_key).strip())

            if not raw_content:
                continue

            try:
                payload = json.loads(raw_content)
            except (TypeError, json.JSONDecodeError):
                continue

            if content_hash := str(payload.get("content_hash") or "").strip():
                existing_keys.add(content_hash)

        return existing_keys

    @staticmethod
    def _entry_key(entry: dict[str, Any]) -> str:
        content_hash = str(entry.get("content_hash") or "").strip()
        if content_hash:
            return content_hash

        return str(entry.get("record_key", "")).strip()

    async def _get_or_create_source_system(
        self, session: AsyncSession
    ) -> DataSourceSystem:
        source_system = await self.source_repository.get_by_name(
            session, self.source_name
        )
        if source_system is not None:
            return source_system

        return await self.source_service.create(
            session,
            DataSourceCreate(
                name=self.source_name,
                source_type=SourceType.BIGDATA,
                description="Extraction processing of Common Crawl datasets via Google BigQuery SQL pipelines.",
                owner_name="Sicurre Crawling Engine",
                legal_basis="public_domain_web_archive",
                contains_personal_data=False,
                retention_days=180,
            ),
        )

    async def _write_snapshot(
        self,
        *,
        ingestion_run: DataIngestionRun,
        payload: dict[str, Any],
    ) -> SnapshotWriteResult:
        snapshot_bytes = json.dumps(
            payload, ensure_ascii=False, indent=2, sort_keys=True
        ).encode("utf-8")
        date_str = ingestion_run.started_at.strftime("%Y%m%d")
        filename = f"common_crawl_extract_{date_str}_{ingestion_run.id}.json"

        object_key = self.snapshot_store.build_object_key(
            source_prefix=self.snapshot_prefix,
            filename=filename,
        )
        return await self.snapshot_store.write_snapshot(
            object_key=object_key,
            payload=snapshot_bytes,
            content_type="application/json",
        )

    def _build_raw_object(
        self,
        *,
        ingestion_run: DataIngestionRun,
        source_system: DataSourceSystem,
        snapshot_result: SnapshotWriteResult,
        collected_at: datetime,
        entry_count: int,
    ) -> DataRawObject:
        return DataRawObject(
            ingestion_run_id=ingestion_run.id,
            external_ref=f"bigquery://{self.bq_client.full_table_id}#run:{ingestion_run.id}",
            object_type=ObjectType.BIGDATA_EXTRACT,
            storage_uri=snapshot_result.storage_uri,
            source_format="json",
            content_hash=snapshot_result.content_hash,
            size_bytes=snapshot_result.size_bytes,
            source_metadata={
                "source_name": source_system.name,
                "entry_count": entry_count,
            },
            collected_at=collected_at,
        )

    def _build_raw_records(
        self,
        *,
        raw_object: DataRawObject,
        entries: list[dict[str, Any]],
        source_system: DataSourceSystem,
    ) -> list[DataRawRecord]:
        extracted_at = datetime.now(timezone.utc)
        raw_records: list[DataRawRecord] = []

        for entry in entries:
            record_key = self._entry_key(entry)

            # Map BigQuery output to Standard sicurre format
            url = entry.get("url", "")
            raw_text = entry.get("text", "")
            original_label = str(entry.get("label") or "").strip() or None
            query_label = (
                str(entry.get("query_label") or original_label or "").strip() or None
            )
            category = str(entry.get("category") or "").strip() or None

            binary_label: int | None
            if category == "phishing_related" or original_label == "phishing":
                binary_label = 1
            elif category in {"legitimate", "spam_like"}:
                binary_label = 0
            else:
                binary_label = None

            enriched = {
                "url": url,
                "text": raw_text,
                "label": original_label,
                "binary_label": binary_label,
                "category": category,
                "crawl_id": entry.get("crawl_id"),
                "query": entry.get("query"),
                "query_label": query_label,
                "content_hash": entry.get("content_hash"),
            }

            raw_content = json.dumps(enriched, ensure_ascii=False, sort_keys=True)
            is_usable = bool(raw_text)
            rejection_reason = None if is_usable else "missing_text_payload"

            raw_records.append(
                DataRawRecord(
                    raw_object_id=raw_object.id,
                    source_system_id=source_system.id,
                    record_key=record_key,
                    raw_content=raw_content,
                    detected_language=entry.get("language", "fr"),
                    is_usable=is_usable,
                    rejection_reason=rejection_reason,
                    extracted_at=extracted_at,
                )
            )

        return raw_records
