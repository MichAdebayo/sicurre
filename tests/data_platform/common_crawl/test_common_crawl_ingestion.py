from __future__ import annotations

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

    monkeypatch.setattr(module.bigquery, "Client", lambda: _FakeBigQueryClient())
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
