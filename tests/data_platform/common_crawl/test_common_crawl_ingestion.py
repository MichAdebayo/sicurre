from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd

from data_platform.extractors import common_crawl_ingestion as module


class _FakeBigQueryClient:
    pass


def test_common_crawl_bigquery_client_uses_settings_for_configuration(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_boto3_client(service_name: str, **kwargs: object) -> object:
        captured["service_name"] = service_name
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        module.CommonCrawlBigQueryClient,
        "_create_bigquery_client",
        staticmethod(lambda: (_FakeBigQueryClient(), object())),
    )
    monkeypatch.setattr(module.boto3, "client", fake_boto3_client)

    settings = module.CommonCrawlIngestionSettings(
        gcp_project="sicurre-test",
        gcp_region="europe-west9",
        dataset_id="sicurre_dataset_test",
        raw_snapshot_r2_bucket_name="sicurre-raw-test",
        raw_snapshot_r2_endpoint_url="https://example-r2.test",
        raw_snapshot_r2_access_key_id="access-key",
        raw_snapshot_r2_secret_access_key="secret-key",
        raw_snapshot_r2_region="auto",
    )

    client = module.CommonCrawlBigQueryClient(settings=settings)

    assert client.project_id == "sicurre-test"
    assert client.dataset_id == "sicurre_dataset_test"
    assert client.r2_bucket == "sicurre-raw-test"
    assert captured == {
        "service_name": "s3",
        "endpoint_url": "https://example-r2.test",
        "aws_access_key_id": "access-key",
        "aws_secret_access_key": "secret-key",
        "region_name": "auto",
    }


def test_local_common_crawl_client_reads_from_bigdata_archive_folder() -> None:
    settings = module.Settings(raw_snapshot_local_dir=Path("/tmp/cron-cache"))

    client = module.LocalCommonCrawlClient(settings=settings)

    assert client.local_parquet_dir == module.DEFAULT_CC_SNAPSHOT_DIR / "fr_usable"


class _FakeS3Client:
    def __init__(self, objects: dict[str, tuple[bytes, datetime]]) -> None:
        self.objects = objects

    def list_objects_v2(self, Bucket: str, Prefix: str) -> dict[str, object]:
        return {
            "Contents": [
                {
                    "Key": key,
                    "LastModified": last_modified,
                }
                for key, (_, last_modified) in self.objects.items()
                if key.startswith(Prefix)
            ]
        }

    def download_fileobj(self, bucket: str, key: str, fileobj) -> None:
        payload, _ = self.objects[key]
        fileobj.write(payload)


def _parquet_bytes(rows: list[dict[str, object]]) -> bytes:
    buffer = BytesIO()
    pd.DataFrame(rows).to_parquet(buffer, index=False, engine="pyarrow")
    return buffer.getvalue()


def test_recovery_snapshot_builder_materializes_local_merged_parquet(
    monkeypatch,
    tmp_path,
) -> None:
    older_key = "raw-snapshots/bigdata/common_crawl/fr_usable/common_crawl_fr_usable_2_20260401_120000.parquet"
    newer_key = "raw-snapshots/bigdata/common_crawl/fr_usable/common_crawl_fr_usable_2_20260402_120000.parquet"
    objects = {
        older_key: (
            _parquet_bytes(
                [
                    {"text": "alpha", "content_hash": "h1"},
                    {"text": "beta", "content_hash": "h2"},
                ]
            ),
            datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
        ),
        newer_key: (
            _parquet_bytes(
                [
                    {"text": "beta", "content_hash": "h2"},
                    {"text": "gamma", "content_hash": "h3"},
                ]
            ),
            datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
        ),
    }

    monkeypatch.setattr(
        module.boto3,
        "client",
        lambda service_name, **kwargs: _FakeS3Client(objects),
    )

    builder = module.CommonCrawlRecoverySnapshotBuilder(
        settings=module.CommonCrawlIngestionSettings(
            raw_snapshot_r2_bucket_name="sicurre-raw-test",
            raw_snapshot_r2_endpoint_url="https://example-r2.test",
            raw_snapshot_r2_access_key_id="access-key",
            raw_snapshot_r2_secret_access_key="secret-key",
            raw_snapshot_r2_region="auto",
        ),
        snapshot_dir=tmp_path / "common_crawl",
    )

    artifact = builder.materialize_local_snapshot(parquet_count=2)

    assert artifact.local_parquet_path.exists()
    assert artifact.manifest_path.exists()
    assert artifact.selected_object_keys == (older_key, newer_key)

    frame = pd.read_parquet(artifact.local_parquet_path)
    assert set(frame["content_hash"].tolist()) == {"h1", "h2", "h3"}

    manifest = json.loads(artifact.manifest_path.read_text(encoding="utf-8"))
    assert manifest["row_count"] == 3
    assert manifest["selected_object_keys"] == [older_key, newer_key]
