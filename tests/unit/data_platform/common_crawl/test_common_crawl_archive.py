from __future__ import annotations

import json

import pandas as pd

from data_platform.cli.bigdata.common_crawl_extract import (
    resolve_crawl_indices,
    resolve_queries,
)
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


def test_resolve_queries_phishing_refresh_excludes_legitimate_queries() -> None:
    queries = resolve_queries("phishing-refresh")

    assert queries is not None
    assert {query.category for query in queries} == {"phishing_related", "spam_like"}
    assert {query.pattern for query in queries} == {
        "signal-arnaques.com/*",
        "cybermalveillance.gouv.fr/*",
        "urlscan.io/result/*",
        "signal-spam.fr/*",
        "openphish.com/*",
        "abuse.ch/*",
        "*.cdiscount.com/newsletter*",
    }


def test_resolve_crawl_indices_phishing_refresh_uses_bounded_recent_indices() -> None:
    indices = resolve_crawl_indices("phishing-refresh")

    assert indices == (
        "CC-MAIN-2025-08",
        "CC-MAIN-2024-51",
        "CC-MAIN-2024-42",
    )


def test_prepare_download_frame_balances_categories_and_query_labels() -> None:
    extractor = CommonCrawlArchiveExtractor(settings=CommonCrawlArchiveSettings())
    extractor.settings.max_warc_downloads = 6
    dataframe = pd.DataFrame(
        [
            {
                "url": "https://phish-a.example/1",
                "status": "200",
                "mime": "text/html",
                "_category": "phishing_related",
                "_label": "phish_a",
                "_query": "phish-a/*",
                "_url_priority_score": 9,
            },
            {
                "url": "https://phish-a.example/2",
                "status": "200",
                "mime": "text/html",
                "_category": "phishing_related",
                "_label": "phish_a",
                "_query": "phish-a/*",
                "_url_priority_score": 8,
            },
            {
                "url": "https://phish-b.example/1",
                "status": "200",
                "mime": "text/html",
                "_category": "phishing_related",
                "_label": "phish_b",
                "_query": "phish-b/*",
                "_url_priority_score": 7,
            },
            {
                "url": "https://spam-a.example/1",
                "status": "200",
                "mime": "text/html",
                "_category": "spam_like",
                "_label": "spam_a",
                "_query": "spam-a/*",
                "_url_priority_score": 9,
            },
            {
                "url": "https://spam-b.example/1",
                "status": "200",
                "mime": "text/html",
                "_category": "spam_like",
                "_label": "spam_b",
                "_query": "spam-b/*",
                "_url_priority_score": 8,
            },
            {
                "url": "https://bank-a.example/1",
                "status": "200",
                "mime": "text/html",
                "_category": "legitimate",
                "_label": "bank_a",
                "_query": "bank-a/*",
                "_url_priority_score": 10,
            },
            {
                "url": "https://bank-a.example/2",
                "status": "200",
                "mime": "text/html",
                "_category": "legitimate",
                "_label": "bank_a",
                "_query": "bank-a/*",
                "_url_priority_score": 9,
            },
            {
                "url": "https://bank-b.example/1",
                "status": "200",
                "mime": "text/html",
                "_category": "legitimate",
                "_label": "bank_b",
                "_query": "bank-b/*",
                "_url_priority_score": 8,
            },
        ]
    )

    selected = extractor._prepare_download_frame(dataframe)

    assert len(selected) == 6
    assert selected["_category"].value_counts().to_dict() == {
        "phishing_related": 2,
        "spam_like": 2,
        "legitimate": 2,
    }
    legitimate_labels = set(
        selected.loc[selected["_category"] == "legitimate", "_label"].tolist()
    )
    assert legitimate_labels == {"bank_a", "bank_b"}


def test_prepare_download_frame_redistributes_unused_category_capacity() -> None:
    extractor = CommonCrawlArchiveExtractor(settings=CommonCrawlArchiveSettings())
    extractor.settings.max_warc_downloads = 5
    dataframe = pd.DataFrame(
        [
            {
                "url": "https://phish-a.example/1",
                "status": "200",
                "mime": "text/html",
                "_category": "phishing_related",
                "_label": "phish_a",
                "_query": "phish-a/*",
                "_url_priority_score": 9,
            },
            {
                "url": "https://phish-b.example/1",
                "status": "200",
                "mime": "text/html",
                "_category": "phishing_related",
                "_label": "phish_b",
                "_query": "phish-b/*",
                "_url_priority_score": 8,
            },
            {
                "url": "https://spam-a.example/1",
                "status": "200",
                "mime": "text/html",
                "_category": "spam_like",
                "_label": "spam_a",
                "_query": "spam-a/*",
                "_url_priority_score": 7,
            },
            {
                "url": "https://bank-a.example/1",
                "status": "200",
                "mime": "text/html",
                "_category": "legitimate",
                "_label": "bank_a",
                "_query": "bank-a/*",
                "_url_priority_score": 10,
            },
            {
                "url": "https://bank-b.example/1",
                "status": "200",
                "mime": "text/html",
                "_category": "legitimate",
                "_label": "bank_b",
                "_query": "bank-b/*",
                "_url_priority_score": 9,
            },
        ]
    )

    selected = extractor._prepare_download_frame(dataframe)

    assert len(selected) == 5
    assert selected["_category"].value_counts().to_dict() == {
        "phishing_related": 2,
        "spam_like": 1,
        "legitimate": 2,
    }


def test_build_quality_report_includes_selection_distribution() -> None:
    settings = CommonCrawlArchiveSettings()
    tracker = type(
        "Tracker",
        (),
        {
            "total_index_hits": 12,
            "total_downloaded": 6,
            "extracted": 5,
            "download_errors": 1,
            "skipped_short": 0,
            "skipped_duplicate": 1,
            "per_language": {"fr": 5},
            "per_category": {"phishing_related": 2, "legitimate": 3},
        },
    )()
    download_frame = pd.DataFrame(
        [
            {
                "_category": "phishing_related",
                "_label": "phish_a",
                "_query": "phish-a/*",
            },
            {"_category": "spam_like", "_label": "spam_a", "_query": "spam-a/*"},
            {"_category": "legitimate", "_label": "bank_a", "_query": "bank-a/*"},
        ]
    )

    report = CommonCrawlArchiveExtractor.build_quality_report(
        timestamp="20260410_120000",
        settings=settings,
        tracker=tracker,
        download_frame=download_frame,
        usable_french_count=3,
    )

    assert report["selection_distribution"]["category"] == {
        "phishing_related": 1,
        "spam_like": 1,
        "legitimate": 1,
    }
    assert report["selection_distribution"]["label"] == {
        "phish_a": 1,
        "spam_a": 1,
        "bank_a": 1,
    }
