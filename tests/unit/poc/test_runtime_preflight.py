"""Tests for secret-safe local POC readiness checks."""

from pathlib import Path

from poc.config import PocSettings
from poc.runtime_preflight import blocking_failures, build_runtime_checks


def settings(tmp_path: Path, **overrides: object) -> PocSettings:
    """Build isolated POC settings without reading developer configuration."""
    values: dict[str, object] = {
        "database_url": f"sqlite:///{tmp_path / 'auth.db'}",
        "data_platform_database_url": f"sqlite:///{tmp_path / 'data.db'}",
        "inference_api_url": "http://127.0.0.1:8000/v1/classify",
        "inference_api_key": "internal-key",
        "admin_password": "admin-password",
        "viewer_password": "viewer-password",
        "_env_file": None,
    }
    values.update(overrides)
    return PocSettings(**values)


def test_runtime_checks_report_names_without_secret_values(tmp_path: Path) -> None:
    """Readiness output carries stable keys and never embeds configured secrets."""
    configured = settings(tmp_path)
    configured.auth_database_path.touch()
    checks = build_runtime_checks(
        configured,
        configured.auth_database_path,
        configured.data_platform_database_path,
        inference_ready=False,
    )
    assert not blocking_failures(checks)
    assert (
        next(check for check in checks if check.key == "preflight_inference_endpoint").ready
        is False
    )
    assert all("internal-key" not in check.key for check in checks)


def test_missing_required_credentials_are_blocking(tmp_path: Path) -> None:
    """Missing local credentials block startup while optional evidence does not."""
    configured = settings(tmp_path, admin_password="", inference_api_key="")
    failures = blocking_failures(
        build_runtime_checks(
            configured,
            configured.auth_database_path,
            configured.data_platform_database_path,
        )
    )
    assert {failure.key for failure in failures} == {
        "preflight_admin_credentials",
        "preflight_inference_key",
        "preflight_auth_database",
    }
