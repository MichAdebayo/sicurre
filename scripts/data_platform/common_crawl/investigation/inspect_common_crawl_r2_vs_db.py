from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import boto3
import pandas as pd
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[4]
ENV_FILE = ROOT_DIR / ".env"
DEFAULT_DB_PATH = ROOT_DIR / "data" / "local" / "sicurre.db"
R2_FR_USABLE_PREFIX = "raw-snapshots/bigdata/common_crawl/fr_usable/"


def _build_s3_client() -> tuple[Any, str]:
    load_dotenv(ENV_FILE)
    r2_bucket = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_BUCKET_NAME", "sicurre-raw")
    endpoint = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_ENDPOINT_URL")
    access_key = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_SECRET_ACCESS_KEY")
    region = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_REGION", "auto")
    if not all([endpoint, access_key, secret_key]):
        raise RuntimeError("Missing R2 credentials in .env")

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    return client, r2_bucket


def _latest_parquet_metadata(s3_client: Any, bucket: str) -> dict[str, Any]:
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=R2_FR_USABLE_PREFIX)
    objects = [
        obj for obj in response.get("Contents", []) if obj["Key"].endswith(".parquet")
    ]
    if not objects:
        raise FileNotFoundError(
            f"No parquet files found in r2://{bucket}/{R2_FR_USABLE_PREFIX}"
        )
    latest = max(objects, key=lambda item: item["LastModified"])
    return {
        "key": latest["Key"],
        "size": latest["Size"],
        "last_modified": str(latest["LastModified"]),
    }


def _load_parquet_frame(s3_client: Any, bucket: str, key: str) -> pd.DataFrame:
    buf = io.BytesIO()
    s3_client.download_fileobj(bucket, key, buf)
    buf.seek(0)
    return pd.read_parquet(buf, engine="pyarrow")


def _counter_from_series(values: pd.Series, *, limit: int = 10) -> dict[str, int]:
    counts = Counter(str(value) for value in values.fillna("<null>").tolist())
    return dict(counts.most_common(limit))


def _load_db_records(db_path: Path) -> tuple[sqlite3.Row, list[dict[str, Any]]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    raw_object_row = conn.execute(
        """
        select ro.id, ro.storage_uri, ro.external_ref, ro.created_at,
               ir.id as ingestion_run_id, ir.started_at, ir.raw_record_count
        from data_raw_object ro
        join data_ingestion_run ir on ir.id = ro.ingestion_run_id
        join data_source_system ss on ss.id = ir.source_system_id
        where ss.name = 'common-crawl-bigdata'
        order by ro.created_at desc
        limit 1
        """
    ).fetchone()
    if raw_object_row is None:
        raise RuntimeError("No DB-backed Common Crawl raw object found")

    db_rows = conn.execute(
        """
        select record_key, raw_content
        from data_raw_record
        where raw_object_id = ?
        """,
        (raw_object_row["id"],),
    ).fetchall()
    records: list[dict[str, Any]] = []
    for row in db_rows:
        payload = json.loads(row["raw_content"])
        payload["record_key"] = row["record_key"]
        records.append(payload)
    conn.close()
    return raw_object_row, records


def _fetch_snapshot_payload(s3_client: Any, storage_uri: str) -> dict[str, Any]:
    _, rest = storage_uri.split("://", 1)
    bucket, key = rest.split("/", 1)
    body = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
    return json.loads(body)


def main() -> None:
    s3_client, bucket = _build_s3_client()
    parquet_meta = _latest_parquet_metadata(s3_client, bucket)
    parquet_df = _load_parquet_frame(s3_client, bucket, parquet_meta["key"])

    raw_object_row, db_records = _load_db_records(DEFAULT_DB_PATH)
    snapshot_payload = _fetch_snapshot_payload(s3_client, raw_object_row["storage_uri"])

    parquet_hashes = {
        str(value).strip()
        for value in parquet_df.get("content_hash", pd.Series(dtype=str))
        .dropna()
        .tolist()
        if str(value).strip()
    }
    db_hashes = {
        str(record.get("content_hash") or "").strip()
        for record in db_records
        if str(record.get("content_hash") or "").strip()
    }
    snapshot_hashes = {
        str(record.get("content_hash") or "").strip()
        for record in snapshot_payload.get("records", [])
        if str(record.get("content_hash") or "").strip()
    }

    db_query_counter = Counter(
        str(record.get("query") or "<null>") for record in db_records
    )
    db_label_counter = Counter(
        str(record.get("label") or "<null>") for record in db_records
    )
    db_category_counter = Counter(
        str(record.get("category") or "<null>") for record in db_records
    )
    db_query_label_counter = Counter(
        str(record.get("query_label") or "<null>") for record in db_records
    )

    summary = {
        "r2_latest_fr_usable_parquet": {
            **parquet_meta,
            "row_count": len(parquet_df),
            "category_summary": _counter_from_series(parquet_df["category"]),
            "label_summary": _counter_from_series(parquet_df["label"]),
            "query_summary": _counter_from_series(parquet_df["query"]),
        },
        "db_latest_common_crawl_raw_object": {
            "raw_object_id": raw_object_row["id"],
            "ingestion_run_id": raw_object_row["ingestion_run_id"],
            "started_at": raw_object_row["started_at"],
            "created_at": raw_object_row["created_at"],
            "storage_uri": raw_object_row["storage_uri"],
            "external_ref": raw_object_row["external_ref"],
            "raw_record_count": raw_object_row["raw_record_count"],
            "category_summary": dict(db_category_counter.most_common(10)),
            "label_summary": dict(db_label_counter.most_common(10)),
            "query_summary": dict(db_query_counter.most_common(10)),
            "query_label_summary": dict(db_query_label_counter.most_common(10)),
        },
        "r2_snapshot_json_for_db_object": {
            "source": snapshot_payload.get("source"),
            "extracted_at": snapshot_payload.get("extracted_at"),
            "record_count": len(snapshot_payload.get("records", [])),
        },
        "overlap": {
            "parquet_vs_db_content_hash_intersection": len(parquet_hashes & db_hashes),
            "parquet_vs_db_raw_object_hash_intersection": len(
                parquet_hashes & snapshot_hashes
            ),
            "db_vs_snapshot_json_hash_intersection": len(db_hashes & snapshot_hashes),
            "parquet_hash_count": len(parquet_hashes),
            "db_hash_count": len(db_hashes),
            "snapshot_json_hash_count": len(snapshot_hashes),
        },
    }

    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
