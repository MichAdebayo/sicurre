from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from core.config import Settings
from core.security import (
    _principal_from_better_auth_payload,
    _validate_with_better_auth,
    extract_bearer_token,
    require_authenticated_principal,
    require_internal_key,
)

TEST_SECRET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def _request(*, cookie: str | None = None) -> Request:
    headers = [] if cookie is None else [(b"cookie", cookie.encode())]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def test_extract_bearer_token_rejects_malformed_headers() -> None:
    assert extract_bearer_token(None) is None
    assert extract_bearer_token("Basic token") is None
    assert extract_bearer_token("Bearer") is None
    assert extract_bearer_token("Bearer  token ") == "token"


@pytest.mark.parametrize(
    ("payload", "subject", "email"),
    [
        (
            {"user": {"id": "u1", "email": "one@example.test"}, "session": {"id": "s1"}},
            "u1",
            "one@example.test",
        ),
        ({"data": {"user": {"name": "Ada"}, "session": {"userId": "u2"}}}, "u2", None),
    ],
)
def test_principal_parses_supported_better_auth_payloads(
    payload: dict[str, Any], subject: str, email: str | None
) -> None:
    principal = _principal_from_better_auth_payload(payload)

    assert principal is not None
    assert principal.subject == subject
    assert principal.email == email


def test_principal_rejects_payload_without_identity() -> None:
    assert _principal_from_better_auth_payload({"session": {}}) is None


@pytest.mark.asyncio
async def test_better_auth_validation_never_caches_revocable_sessions(monkeypatch) -> None:
    """A revoked cookie must be rejected on the request immediately after logout."""
    responses = iter(
        [
            httpx.Response(
                200,
                json={"user": {"id": "active-user"}},
                request=httpx.Request("GET", "http://auth/session"),
            ),
            httpx.Response(401),
        ]
    )

    class Client:
        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def get(self, *_: Any, **__: Any) -> httpx.Response:
            return next(responses)

    monkeypatch.setattr("core.security.httpx.AsyncClient", lambda **_: Client())
    settings = Settings(_env_file=None)

    assert await _validate_with_better_auth(None, settings, "cookie") is not None
    assert await _validate_with_better_auth(None, settings, "cookie") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403])
async def test_better_auth_validation_rejects_denied_session(monkeypatch, status_code: int) -> None:
    class Client:
        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def get(self, *_: Any, **__: Any) -> httpx.Response:
            return httpx.Response(status_code)

    monkeypatch.setattr("core.security.httpx.AsyncClient", lambda **_: Client())

    assert await _validate_with_better_auth("denied", Settings(_env_file=None)) is None


@pytest.mark.asyncio
async def test_better_auth_validation_sends_session_cookie(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class Client:
        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def get(self, _: str, *, headers: dict[str, str]) -> httpx.Response:
            captured.update(headers)
            return httpx.Response(
                200,
                json={"user": {"id": "cookie-user"}},
                request=httpx.Request("GET", "http://auth/session"),
            )

    monkeypatch.setattr("core.security.httpx.AsyncClient", lambda **_: Client())
    settings = Settings(_env_file=None, better_auth_cookie_name="session")

    principal = await _validate_with_better_auth(
        None,
        settings,
        "cookie-value",
        client_ip="203.0.113.10",
    )

    assert principal is not None
    assert principal.subject == "cookie-user"
    assert captured == {
        "Cookie": "session=cookie-value",
        "x-real-ip": "203.0.113.10",
    }


@pytest.mark.asyncio
async def test_auth_disabled_attaches_anonymous_principal() -> None:
    request = _request()

    principal = await require_authenticated_principal(
        request,
        None,
        Settings(_env_file=None, auth_enabled=False),
    )

    assert principal.auth_provider == "disabled"
    assert request.state.auth_principal == principal


@pytest.mark.asyncio
async def test_dev_token_authentication_and_invalid_token() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        auth_dev_bearer_tokens="accepted",
        better_auth_base_url=None,
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="accepted")

    principal = await require_authenticated_principal(_request(), credentials, settings)

    assert principal.auth_provider == "development"

    with pytest.raises(HTTPException) as exc_info:
        await require_authenticated_principal(
            _request(),
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong"),
            settings,
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_authentication_reports_missing_and_unavailable_services() -> None:
    with pytest.raises(HTTPException) as missing:
        await require_authenticated_principal(_request(), None, Settings(_env_file=None))
    assert missing.value.status_code == 401

    settings = Settings(
        _env_file=None,
        environment="production",
        auth_allow_dev_tokens=False,
        better_auth_base_url=None,
        secret_encryption_key=TEST_SECRET_KEY,
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
    with pytest.raises(HTTPException) as unavailable:
        await require_authenticated_principal(_request(), credentials, settings)
    assert unavailable.value.status_code == 503


@pytest.mark.asyncio
async def test_internal_key_contract() -> None:
    with pytest.raises(HTTPException) as missing:
        await require_internal_key(None, Settings(_env_file=None, internal_api_key=None))
    assert missing.value.status_code == 503

    settings = Settings(_env_file=None).model_copy(update={"internal_api_key": "expected"})
    with pytest.raises(HTTPException) as invalid:
        await require_internal_key(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong"), settings
        )
    assert invalid.value.status_code == 401

    assert (
        await require_internal_key(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="expected"), settings
        )
        is None
    )
