"""Shared R2 helpers for the freeze proof scripts.

All freeze proof scripts are read-only with respect to existing R2 objects —
they write only to new ``base/`` or ``proof`` prefixes and never overwrite
anything that was there before the freeze.
"""

from __future__ import annotations

import hashlib
import io
import os
import sqlite3
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv


def build_s3_client(env_file: Path) -> tuple[Any, str]:
    load_dotenv(env_file)
    bucket = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_BUCKET_NAME", "sicurre-raw")
    endpoint = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_ENDPOINT_URL")
    access_key = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_SECRET_ACCESS_KEY")
    region = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_REGION", "auto")
    if not all([endpoint, access_key, secret_key]):
        raise RuntimeError(
            "Missing R2 credentials in .env — set SICURRE_RAW_SNAPSHOT_R2_* vars"
        )
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    return s3, bucket


def key_exists(s3: Any, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise


def list_keys(s3: Any, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return sorted(keys)


def download_bytes(s3: Any, bucket: str, key: str) -> bytes:
    buf = io.BytesIO()
    s3.download_fileobj(bucket, key, buf)
    return buf.getvalue()


def upload_bytes(
    s3: Any, bucket: str, key: str, payload: bytes, content_type: str
) -> None:
    s3.put_object(Bucket=bucket, Key=key, Body=payload, ContentType=content_type)


def s3_copy(s3: Any, bucket: str, src_key: str, dst_key: str) -> None:
    """Copy an object within the same R2 bucket."""
    s3.copy_object(
        Bucket=bucket,
        CopySource={"Bucket": bucket, "Key": src_key},
        Key=dst_key,
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_db_source_counts(db_path: Path) -> dict[str, int]:
    """Return {source_name: row_count} from sicurre.db for all sources."""
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        sources = conn.execute("SELECT id, name FROM data_source_system").fetchall()
        result: dict[str, int] = {}
        for sid, name in sources:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM data_raw_record WHERE source_system_id = ?",
                (sid,),
            ).fetchone()[0]
            result[name] = cnt
        return result
    finally:
        conn.close()
