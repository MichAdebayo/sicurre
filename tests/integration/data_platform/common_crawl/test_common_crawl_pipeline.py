from __future__ import annotations

import asyncio
from argparse import Namespace
from pathlib import Path

from data_platform.cli.bigdata import common_crawl_pipeline as module


def test_run_pipeline_materializes_recovery_when_ingest_is_skipped(monkeypatch) -> None:
    async def failing_run_extraction(*, settings, query_profile):
        raise RuntimeError("No raw index hits found.")

    async def unexpected_run_ingestion(*, trigger_mode: str = "manual"):
        raise AssertionError("run_ingestion should not be called when skip_ingest=True")

    monkeypatch.setattr(module, "build_settings", lambda args: object())
    monkeypatch.setattr(module, "run_extraction", failing_run_extraction)
    monkeypatch.setattr(module, "run_ingestion", unexpected_run_ingestion)

    class _Artifact:
        local_parquet_path = (
            Path(module.ROOT_DIR)
            / "data/raw/bigdata/common_crawl/fr_usable/recovery.parquet"
        )
        manifest_path = (
            Path(module.ROOT_DIR)
            / "data/raw/bigdata/common_crawl/quality/recovery.json"
        )
        selected_object_keys = (
            "raw-snapshots/bigdata/common_crawl/fr_usable/a.parquet",
            "raw-snapshots/bigdata/common_crawl/fr_usable/b.parquet",
        )
        row_count = 42

    monkeypatch.setattr(
        module,
        "_materialize_local_recovery_snapshot",
        lambda *, fallback_mode, recovery_parquet_count: _Artifact(),
    )

    payload = asyncio.run(
        module.run_pipeline(
            trigger_mode="manual",
            skip_extract=False,
            skip_ingest=True,
            extraction_args=Namespace(
                max_results_per_query=80,
                max_warc_downloads=80,
                target_records=50,
                async_concurrency=6,
                min_text_length=None,
                max_text_length=None,
                request_timeout=15,
                batch_size=20,
                query_profile="phishing-refresh",
                fallback_mode="merge-r2-local",
                recovery_parquet_count=2,
                log_level="INFO",
            ),
        )
    )

    assert payload["extraction_error"] == {
        "type": "RuntimeError",
        "message": "No raw index hits found.",
    }
    assert payload["recovery"] == {
        "mode": "merge-r2-local",
        "row_count": 42,
        "local_parquet_path": "data/raw/bigdata/common_crawl/fr_usable/recovery.parquet",
        "manifest_path": "data/raw/bigdata/common_crawl/quality/recovery.json",
        "selected_object_keys": [
            "raw-snapshots/bigdata/common_crawl/fr_usable/a.parquet",
            "raw-snapshots/bigdata/common_crawl/fr_usable/b.parquet",
        ],
    }
    assert "ingestion" not in payload
