"""Tests for the isolated local POC configuration contract."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from poc.config import PocSettings, sqlite_path


def settings(**overrides: object) -> PocSettings:
    """Build settings without reading the developer's local environment file."""
    values = {
        "database_url": "sqlite+aiosqlite:////tmp/sicurre-poc-auth.db",
        "data_platform_database_url": "sqlite+aiosqlite:////tmp/sicurre-poc-data.db",
        "inference_api_url": "http://127.0.0.1:8000/v1/classify",
        "inference_api_key": "test-key",
        "admin_password": "admin-secret",
        "viewer_password": "viewer-secret",
    }
    values.update(overrides)
    return PocSettings(_env_file=None, **values)


def test_sqlite_path_supports_sync_and_async_urls() -> None:
    assert sqlite_path("sqlite:////tmp/sync.db") == Path("/tmp/sync.db")
    assert sqlite_path("sqlite+aiosqlite:////tmp/async.db") == Path("/tmp/async.db")


def test_remote_poc_database_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must use SQLite"):
        settings(database_url="postgresql://example.invalid/sicurre")


def test_classifier_contract_requires_classify_route() -> None:
    with pytest.raises(ValidationError, match="must end with /v1/classify"):
        settings(inference_api_url="http://127.0.0.1:8000/v1/email/scan")


def test_external_namespace_must_be_a_demonstration_prefix() -> None:
    with pytest.raises(ValidationError, match="must start with demonstrations"):
        settings(r2_prefix="production/monthly")


def test_required_demo_credentials_are_reported_together() -> None:
    configured = settings(
        inference_api_key="",
        admin_password="",
        viewer_password="",
    )
    with pytest.raises(RuntimeError) as error:
        configured.require_demo_credentials()
    assert "SICURRE_POC_INFERENCE_API_KEY" in str(error.value)
    assert "SICURRE_POC_ADMIN_PASSWORD" in str(error.value)
    assert "SICURRE_POC_VIEWER_PASSWORD" in str(error.value)
