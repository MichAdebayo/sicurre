from __future__ import annotations

from core.config import Settings


def test_common_crawl_legacy_s3_retry_names_remain_supported(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CC_S3_RETRY_DELAY", "1.5")
    monkeypatch.setenv("CC_S3_MAX_RETRIES", "3")

    settings = Settings()

    assert settings.cc_warc_retry_delay_seconds == 1.5
    assert settings.cc_warc_max_retries == 3


def test_common_crawl_preferred_warc_retry_names_take_precedence(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CC_S3_RETRY_DELAY", "8")
    monkeypatch.setenv("CC_WARC_RETRY_DELAY_SECONDS", "0.5")
    monkeypatch.setenv("CC_S3_MAX_RETRIES", "8")
    monkeypatch.setenv("CC_WARC_MAX_RETRIES", "2")

    settings = Settings()

    assert settings.cc_warc_retry_delay_seconds == 0.5
    assert settings.cc_warc_max_retries == 2
