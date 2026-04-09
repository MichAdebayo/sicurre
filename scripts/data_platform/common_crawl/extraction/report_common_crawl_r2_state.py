from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import pandas as pd
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[4]
ENV_FILE = ROOT_DIR / ".env"
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


def _download_bytes(s3_client: Any, bucket: str, key: str) -> bytes:
    return s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()


def _load_parquet(payload: bytes) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(payload), engine="pyarrow")


def _parse_timestamp_from_key(key: str) -> str:
    match = re.search(r"_(\d{8}_\d{6})\.(?:parquet|json)$", key)
    return match.group(1) if match else "unknown"


def _summarize_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "row_count": len(df),
        "columns": list(df.columns),
    }
    for column in ("category", "label", "query", "language"):
        if column in df.columns:
            summary[f"{column}_summary"] = (
                df[column]
                .fillna("<null>")
                .value_counts(dropna=False)
                .head(15)
                .to_dict()
            )
    if "content_hash" in df.columns:
        hashes = [
            str(value).strip()
            for value in df["content_hash"].dropna().tolist()
            if str(value).strip()
        ]
        summary["content_hash_count"] = len(set(hashes))
    return summary


def _group_objects(objects: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(dict)
    for obj in objects:
        key = obj["key"]
        timestamp = _parse_timestamp_from_key(key)
        if "/raw/" in key:
            grouped[timestamp]["raw"] = obj
        elif "/fr_usable/" in key:
            grouped[timestamp]["fr_usable"] = obj
        elif "/quality/" in key:
            grouped[timestamp]["quality"] = obj
    return dict(grouped)


def _list_objects(s3_client: Any, bucket: str) -> list[dict[str, Any]]:
    prefixes = (
        f"{COMMON_CRAWL_PREFIX}/raw/",
        f"{COMMON_CRAWL_PREFIX}/fr_usable/",
        f"{COMMON_CRAWL_PREFIX}/quality/",
    )
    objects: list[dict[str, Any]] = []
    for prefix in prefixes:
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        objects.extend(
            {
                "key": obj["Key"],
                "size": obj["Size"],
                "last_modified": str(obj["LastModified"]),
            }
            for obj in response.get("Contents", [])
        )
    return sorted(objects, key=lambda item: item["key"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report the current Common Crawl R2 state, per-object checksums, and combined data diversity."
    )
    parser.add_argument(
        "--include-quality",
        action="store_true",
        help="Include full quality report payloads in the per-run output.",
    )
    args = parser.parse_args()

    s3_client, bucket = _build_s3_client()
    objects = _list_objects(s3_client, bucket)
    grouped = _group_objects(objects)

    raw_frames: list[pd.DataFrame] = []
    fr_frames: list[pd.DataFrame] = []
    raw_run_hashes: dict[str, set[str]] = {}
    fr_run_hashes: dict[str, set[str]] = {}
    runs: dict[str, Any] = {}

    for timestamp, family in grouped.items():
        run_entry: dict[str, Any] = {"timestamp": timestamp, "objects": {}}
        for kind, obj in family.items():
            payload = _download_bytes(s3_client, bucket, obj["key"])
            base = {
                **obj,
                "storage_uri": f"r2://{bucket}/{obj['key']}",
                "sha256": _sha256_bytes(payload),
            }
            if kind in {"raw", "fr_usable"}:
                df = _load_parquet(payload)
                base["summary"] = _summarize_dataframe(df)
                hashes = {
                    str(value).strip()
                    for value in df.get("content_hash", pd.Series(dtype=str))
                    .dropna()
                    .tolist()
                    if str(value).strip()
                }
                if kind == "raw":
                    raw_frames.append(df)
                    raw_run_hashes[timestamp] = hashes
                else:
                    fr_frames.append(df)
                    fr_run_hashes[timestamp] = hashes
            else:
                quality_payload = json.loads(payload.decode("utf-8"))
                if args.include_quality:
                    base["payload"] = quality_payload
                else:
                    base["summary"] = {
                        "extraction_date": quality_payload.get("extraction_date"),
                        "stats": quality_payload.get("stats"),
                        "category_distribution": quality_payload.get(
                            "category_distribution"
                        ),
                        "language_distribution": quality_payload.get(
                            "language_distribution"
                        ),
                        "has_provenance": "provenance" in quality_payload,
                    }
            run_entry["objects"][kind] = base
        runs[timestamp] = run_entry

    combined_raw = (
        pd.concat(raw_frames, ignore_index=True) if raw_frames else pd.DataFrame()
    )
    combined_fr = (
        pd.concat(fr_frames, ignore_index=True) if fr_frames else pd.DataFrame()
    )

    def pairwise_overlaps(run_hashes: dict[str, set[str]]) -> dict[str, int]:
        overlaps: dict[str, int] = {}
        timestamps = sorted(run_hashes)
        for index, left in enumerate(timestamps):
            for right in timestamps[index + 1 :]:
                overlaps[f"{left}__{right}"] = len(run_hashes[left] & run_hashes[right])
        return overlaps

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bucket": bucket,
        "prefix": COMMON_CRAWL_PREFIX,
        "run_count": len(runs),
        "runs": runs,
        "combined": {
            "raw": {} if combined_raw.empty else _summarize_dataframe(combined_raw),
            "fr_usable": {} if combined_fr.empty else _summarize_dataframe(combined_fr),
            "raw_pairwise_content_hash_overlap": pairwise_overlaps(raw_run_hashes),
            "fr_usable_pairwise_content_hash_overlap": pairwise_overlaps(fr_run_hashes),
        },
    }

    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
