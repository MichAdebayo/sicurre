"""Secret-safe runtime readiness checks for the local certification POC."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from poc.config import PocSettings


@dataclass(frozen=True)
class RuntimeCheck:
    """A named readiness check that contains no secret value."""

    key: str
    ready: bool
    blocking: bool


def build_runtime_checks(
    settings: PocSettings,
    auth_database_path: Path,
    data_database_path: Path,
    inference_ready: bool | None = None,
) -> list[RuntimeCheck]:
    """Build configuration, persistence, isolation, and inference checks."""
    return [
        RuntimeCheck("preflight_admin_credentials", bool(settings.admin_password), True),
        RuntimeCheck("preflight_viewer_credentials", bool(settings.viewer_password), True),
        RuntimeCheck("preflight_inference_key", bool(settings.inference_api_key), True),
        RuntimeCheck("preflight_auth_database", auth_database_path.is_file(), True),
        RuntimeCheck("preflight_data_database", data_database_path.is_file(), False),
        RuntimeCheck(
            "preflight_local_isolation",
            settings.database_url.startswith("sqlite")
            and settings.data_platform_database_url.startswith("sqlite"),
            True,
        ),
        RuntimeCheck(
            "preflight_inference_endpoint",
            bool(inference_ready),
            False,
        ),
    ]


def blocking_failures(checks: list[RuntimeCheck]) -> list[RuntimeCheck]:
    """Return checks that must pass before local authentication can start."""
    return [check for check in checks if check.blocking and not check.ready]
