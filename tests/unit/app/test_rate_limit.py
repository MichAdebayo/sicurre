"""Rate-limit identity tests for public and authenticated API boundaries."""

from __future__ import annotations

from fastapi.testclient import TestClient
from starlette.requests import Request

from core.rate_limit import get_rate_limit_key
from data_platform.api.main import create_app


def _request(*, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers or [],
            "client": ("192.0.2.10", 4000),
        }
    )


def test_rate_limit_prefers_bearer_identity_without_exposing_token() -> None:
    key = get_rate_limit_key(
        _request(headers=[(b"authorization", b"Bearer customer-secret")])
    )

    assert key.startswith("token:")
    assert "customer-secret" not in key


def test_rate_limit_uses_worker_identity_before_proxy_ip() -> None:
    first = get_rate_limit_key(
        _request(
            headers=[
                (b"x-sicurre-secret", b"worker-one"),
                (b"x-real-ip", b"203.0.113.9"),
            ]
        )
    )
    second = get_rate_limit_key(
        _request(
            headers=[
                (b"x-sicurre-secret", b"worker-two"),
                (b"x-real-ip", b"203.0.113.9"),
            ]
        )
    )

    assert first.startswith("worker:")
    assert first != second


def test_rate_limit_falls_back_to_forwarded_client_ip() -> None:
    key = get_rate_limit_key(_request(headers=[(b"x-real-ip", b"203.0.113.25")]))

    assert key == "ip:203.0.113.25"


def test_rate_limit_uses_hashed_session_identity() -> None:
    """Separate signed-in browser sessions without exposing cookie values."""
    key = get_rate_limit_key(
        _request(headers=[(b"cookie", b"better-auth.session_token=session-secret")])
    )

    assert key.startswith("session:")
    assert "session-secret" not in key


def test_default_limit_applies_to_undecorated_public_routes() -> None:
    """SlowAPI middleware enforces the configured fallback across the API."""
    client = TestClient(create_app())
    headers = {"x-real-ip": "198.51.100.77"}

    for _ in range(120):
        assert client.get("/openapi.json", headers=headers).status_code == 200

    assert client.get("/openapi.json", headers=headers).status_code == 429
    assert client.get("/health", headers=headers).status_code == 200
