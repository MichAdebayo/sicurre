from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import pandas as pd
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[4]
ENV_FILE = ROOT_DIR / ".env"

DEFAULT_RAW_CSV = (
    ROOT_DIR / "data/raw/bigdata/common_crawl/common_crawl_all_1763_20260406.csv"
)
DEFAULT_FR_USABLE_CSV = (
    ROOT_DIR / "data/raw/bigdata/common_crawl/common_crawl_fr_usable_1220_20260406.csv"
)
DEFAULT_QUALITY_JSON = (
    ROOT_DIR / "data/raw/bigdata/common_crawl/quality_report_20260406.json"
)

COMMON_CRAWL_PREFIX = "raw-snapshots/bigdata/common_crawl"


def _build_s3_client() -> tuple[Any, str]:
    load_dotenv(ENV_FILE)
    bucket = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_BUCKET_NAME", "sicurre-raw")
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
    return client, bucket


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def _to_parquet_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow")
    return buffer.getvalue()


def _build_quality_payload(
    *,
    quality_template: dict[str, Any],
    raw_df: pd.DataFrame,
    fr_df: pd.DataFrame,
    timestamp: str,
    raw_csv: Path,
    fr_csv: Path,
    quality_json: Path,
    raw_parquet_sha256: str,
    fr_parquet_sha256: str,
) -> dict[str, Any]:
    payload = dict(quality_template)
    payload["extraction_date"] = timestamp
    payload["stats"] = {
        **(quality_template.get("stats") or {}),
        "total_extracted": len(raw_df),
        "usable_french": len(fr_df),
    }
    payload["language_distribution"] = (
        raw_df["language"].fillna("<null>").value_counts(dropna=False).to_dict()
        if "language" in raw_df.columns
        else {}
    )
    payload["category_distribution"] = (
        raw_df["category"].fillna("<null>").value_counts(dropna=False).to_dict()
        if "category" in raw_df.columns
        else {}
    )
    if "label" in raw_df.columns:
        payload["label_distribution"] = (
            raw_df["label"].fillna("<null>").value_counts(dropna=False).to_dict()
        )
    payload["provenance"] = {
        "mode": "local_backfill_upload",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "source_raw_csv": raw_csv.name,
        "source_fr_usable_csv": fr_csv.name,
        "source_quality_json": quality_json.name,
        "source_raw_csv_sha256": _sha256_bytes(raw_csv.read_bytes()),
        "source_fr_usable_csv_sha256": _sha256_bytes(fr_csv.read_bytes()),
        "source_quality_json_sha256": _sha256_bytes(quality_json.read_bytes()),
        "uploaded_raw_parquet_sha256": raw_parquet_sha256,
        "uploaded_fr_usable_parquet_sha256": fr_parquet_sha256,
    }
    return payload


def _upload_bytes(
    *,
    s3_client: Any,
    bucket: str,
    key: str,
    payload: bytes,
    content_type: str,
) -> dict[str, Any]:
    response = s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=payload,
        ContentType=content_type,
    )
    return {
        "bucket": bucket,
        "key": key,
        "size": len(payload),
        "sha256": _sha256_bytes(payload),
        "etag": str(response.get("ETag") or "").strip('"'),
        "storage_uri": f"r2://{bucket}/{key}",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload a local Common Crawl backfill run to R2 using the same raw/fr_usable/quality contract as the live pipeline."
    )
    parser.add_argument("--raw-csv", type=Path, default=DEFAULT_RAW_CSV)
    parser.add_argument("--fr-usable-csv", type=Path, default=DEFAULT_FR_USABLE_CSV)
    parser.add_argument("--quality-json", type=Path, default=DEFAULT_QUALITY_JSON)
    parser.add_argument(
        "--timestamp",
        type=str,
        default=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
    )
    args = parser.parse_args()

    raw_df = _read_csv(args.raw_csv)
    fr_df = _read_csv(args.fr_usable_csv)
    quality_template = json.loads(args.quality_json.read_text(encoding="utf-8"))

    raw_parquet = _to_parquet_bytes(raw_df)
    fr_parquet = _to_parquet_bytes(fr_df)
    raw_sha256 = _sha256_bytes(raw_parquet)
    fr_sha256 = _sha256_bytes(fr_parquet)

    quality_payload = _build_quality_payload(
        quality_template=quality_template,
        raw_df=raw_df,
        fr_df=fr_df,
        timestamp=args.timestamp,
        raw_csv=args.raw_csv,
        fr_csv=args.fr_usable_csv,
        quality_json=args.quality_json,
        raw_parquet_sha256=raw_sha256,
        fr_parquet_sha256=fr_sha256,
    )
    quality_bytes = json.dumps(
        quality_payload, ensure_ascii=False, indent=2, sort_keys=True
    ).encode("utf-8")

    raw_key = f"{COMMON_CRAWL_PREFIX}/raw/common_crawl_raw_{len(raw_df)}_{args.timestamp}.parquet"
    fr_key = f"{COMMON_CRAWL_PREFIX}/fr_usable/common_crawl_fr_usable_{len(fr_df)}_{args.timestamp}.parquet"
    quality_key = f"{COMMON_CRAWL_PREFIX}/quality/quality_report_{args.timestamp}.json"

    s3_client, bucket = _build_s3_client()
    raw_result = _upload_bytes(
        s3_client=s3_client,
        bucket=bucket,
        key=raw_key,
        payload=raw_parquet,
        content_type="application/vnd.apache.parquet",
    )
    fr_result = _upload_bytes(
        s3_client=s3_client,
        bucket=bucket,
        key=fr_key,
        payload=fr_parquet,
        content_type="application/vnd.apache.parquet",
    )
    quality_result = _upload_bytes(
        s3_client=s3_client,
        bucket=bucket,
        key=quality_key,
        payload=quality_bytes,
        content_type="application/json",
    )

    output = {
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "timestamp": args.timestamp,
        "source_files": {
            "raw_csv": str(args.raw_csv),
            "fr_usable_csv": str(args.fr_usable_csv),
            "quality_json": str(args.quality_json),
        },
        "row_counts": {
            "raw": len(raw_df),
            "fr_usable": len(fr_df),
        },
        "uploads": {
            "raw": raw_result,
            "fr_usable": fr_result,
            "quality": quality_result,
        },
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
