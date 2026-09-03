"""Documentation visibility must not change the API contract or operations."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.config import Settings
from data_platform.api import main

DOC_PATHS = ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect")


@pytest.mark.parametrize(
    ("environment", "expected_status"),
    [
        ("dev", 200),
        ("development", 200),
        ("local", 200),
        ("production", 404),
        ("prod", 404),
        (" Production ", 404),
        ("staging", 404),
        ("", 404),
    ],
)
def test_documentation_visibility(
    monkeypatch: pytest.MonkeyPatch, environment: str, expected_status: int
) -> None:
    """Only explicitly local environments serve reference pages and schemas."""
    settings = Settings(_env_file=None, environment="dev", telemetry_traces_enabled=False)
    monkeypatch.setattr(
        main, "get_settings", lambda: settings.model_copy(update={"environment": environment})
    )
    app = main.create_app()
    client = TestClient(app)

    for path in DOC_PATHS:
        response = client.get(path)
        assert response.status_code == expected_status, path
    assert client.get("/health").status_code == 200
    assert "/v1/email/scan" in app.openapi()["paths"]


def test_production_proxy_blocks_all_documentation_paths() -> None:
    """The public proxy denies docs even before reaching the service guard."""
    root = Path(__file__).resolve().parents[3]
    config = (root / "deploy/nginx/conf.d/sicurre.com.conf").read_text()
    rule = re.search(r"location ~ (\^/.*?) \{([^}]+)\}", config)
    assert rule is not None
    assert "return 404;" in rule.group(2)
    matcher = re.compile(rule.group(1))
    for path in (*DOC_PATHS, "/api/auth/reference", "/api/auth/open-api/generate-schema"):
        assert matcher.match(path), path
        assert matcher.match(path + "/"), path
    for path in ("/health", "/v1/email/scan", "/api/auth/sign-in/email", "/app/dashboard"):
        assert matcher.match(path) is None
