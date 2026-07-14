from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.config import Settings


def test_dev_tokens_allowed_in_dev_by_default() -> None:
    settings = Settings(environment="dev")

    assert settings.allow_dev_tokens is True


def test_dev_tokens_disabled_in_prod_by_default() -> None:
    settings = Settings(environment="prod")

    assert settings.allow_dev_tokens is False


def test_explicit_dev_token_override_wins() -> None:
    settings = Settings(environment="prod", auth_allow_dev_tokens=True)

    assert settings.allow_dev_tokens is True


def test_database_historical_cron_counts_are_configurable() -> None:
    settings = Settings(
        database_historical_cron_total_count=500,
        database_historical_cron_max_total_count=1000,
    )

    assert settings.database_historical_cron_total_count == 500
    assert settings.database_historical_cron_max_total_count == 1000


def test_sicurre_inference_url_overrides_local_fallback(monkeypatch) -> None:
    monkeypatch.setenv("INFERENCE_API_URL", "http://localhost:8000/v1/classify")
    monkeypatch.setenv("SICURRE_INFERENCE_API_URL", "https://api.sicurre.com/v1/classify")

    settings = Settings(_env_file=None)

    assert settings.inference_api_url == "https://api.sicurre.com/v1/classify"


@pytest.mark.parametrize(
    "url",
    ["not-a-url", "https://internal/v1/classify", "https://api.sicurre.com/v1/email/scan"],
)
def test_inference_url_rejects_invalid_classifier_endpoints(monkeypatch, url: str) -> None:
    monkeypatch.setenv("SICURRE_INFERENCE_API_URL", url)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_runtime_urls_and_database_driver_conversion(monkeypatch) -> None:
    monkeypatch.setenv("SICURRE_INFERENCE_API_URL", "https://ml.sicurre.com/v1/classify/")
    monkeypatch.setenv("SICURRE_PUBLIC_API_URL", "https://api.sicurre.com/")
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@db/app",
        data_platform_database_url="sqlite+aiosqlite:///platform.db",
    )

    assert settings.inference_api_url == "https://ml.sicurre.com/v1/classify"
    assert settings.public_api_url == "https://api.sicurre.com"
    assert settings.sync_database_url == "postgresql+psycopg://user:pass@db/app"
    assert settings.sync_data_platform_database_url == "sqlite:///platform.db"


def test_snapshot_override_and_normalized_sets() -> None:
    settings = Settings(
        _env_file=None,
        raw_snapshot_storage_backend="local",
        phishtank_snapshot_storage_backend="r2",
        auth_dev_bearer_tokens=" first, second ,,",
        platform_admin_emails="ADMIN@SICURRE.COM, owner@sicurre.com ",
    )

    assert settings.resolve_snapshot_storage_backend(source_key="phishtank") == "r2"
    assert settings.resolve_snapshot_storage_backend(source_key="unknown") == "local"
    assert settings.dev_bearer_tokens == frozenset({"first", "second"})
    assert settings.platform_admin_email_set == frozenset(
        {"admin@sicurre.com", "owner@sicurre.com"}
    )


def test_better_auth_schema_is_normalized_and_validated() -> None:
    assert (
        Settings(_env_file=None, better_auth_schema=" Identity ").better_auth_schema == "identity"
    )
    with pytest.raises(ValidationError):
        Settings(_env_file=None, better_auth_schema="auth; drop schema")
