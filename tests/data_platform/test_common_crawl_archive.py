from __future__ import annotations

import json

import pandas as pd

from data_platform.extractors.common_crawl_archive import (
    CommonCrawlArchiveExtractor,
    CommonCrawlArchiveSettings,
    CommonCrawlArchiveStore,
    CrawlQuery,
)


class _DummySnapshotStore:
    def build_object_key(self, *, source_prefix: str, filename: str) -> str:
        return f"{source_prefix}/{filename}"


def test_common_crawl_archive_store_uses_local_prefix_for_local_backend() -> None:
    store = CommonCrawlArchiveStore(
        snapshot_store=_DummySnapshotStore(),
        backend="local",
    )

    object_key = store.build_object_key(
        subfolder="raw",
        filename="common_crawl_raw_10_20260410_120000.parquet",
    )

    assert object_key == (
        "raw/bigdata/common_crawl/raw/" "common_crawl_raw_10_20260410_120000.parquet"
    )


def test_parse_index_payload_adds_metadata_and_excludes_domains() -> None:
    extractor = CommonCrawlArchiveExtractor(settings=CommonCrawlArchiveSettings())
    query = CrawlQuery("example.com/*", "phishing_related", "demo_query")
    payload = "\n".join(
        [
            json.dumps(
                {
                    "url": "https://example.com/login",
                    "offset": "1",
                    "length": "10",
                    "filename": "a.warc.gz",
                }
            ),
            json.dumps(
                {
                    "url": "https://phishtank.org/foo",
                    "offset": "2",
                    "length": "10",
                    "filename": "b.warc.gz",
                }
            ),
        ]
    )

    records = extractor._parse_index_payload(
        payload=payload,
        query=query,
        crawl_id="CC-MAIN-2025-08",
    )

    assert len(records) == 1
    assert records[0]["_category"] == "phishing_related"
    assert records[0]["_label"] == "demo_query"
    assert records[0]["_crawl_id"] == "CC-MAIN-2025-08"
    assert records[0]["url"] == "https://example.com/login"


def test_build_usable_frame_keeps_only_french_rows_above_length_threshold() -> None:
    extractor = CommonCrawlArchiveExtractor(
        settings=CommonCrawlArchiveSettings(min_text_length=100)
    )
    dataframe = pd.DataFrame(
        [
            {"url": "https://a.example", "language": "fr", "text_length": 120},
            {"url": "https://b.example", "language": "en", "text_length": 240},
            {"url": "https://c.example", "language": "fr", "text_length": 80},
        ]
    )

    usable = extractor._build_usable_frame(dataframe)

    assert list(usable["url"]) == ["https://a.example"]
