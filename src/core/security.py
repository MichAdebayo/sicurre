from __future__ import annotations

import hashlib
from typing import Any

import httpx
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from core.config import Settings, get_settings


class AuthenticatedPrincipal(BaseModel):
    subject: str
    email: str | None = None
    display_name: str | None = None
    session_id: str | None = None
    auth_provider: str


_bearer_scheme = HTTPBearer(auto_error=False)
_credentials_dependency = Security(_bearer_scheme)
_settings_dependency = Depends(get_settings)


def extract_bearer_token(authorization_header: str | None) -> str | None:
    if authorization_header is None:
        return None

    scheme, _, token = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def extract_better_auth_session_cookie(
    request: Request, configured_name: str
) -> tuple[str, str] | None:
    """Resolve local or HTTPS-prefixed Better Auth session cookies."""
    candidate_names = [configured_name]
    if not configured_name.startswith("__Secure-"):
        candidate_names.insert(0, f"__Secure-{configured_name}")
    for cookie_name in candidate_names:
        cookie_value = request.cookies.get(cookie_name)
        if cookie_value:
            return cookie_name, cookie_value
    return None


def _unauthorized(detail: str = "Authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _principal_from_better_auth_payload(
    payload: dict[str, Any],
) -> AuthenticatedPrincipal | None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else None
    session = payload.get("session") or (data or {}).get("session") or {}
    user = payload.get("user") or (data or {}).get("user") or {}

    subject = user.get("id") or session.get("userId") or session.get("id")
    if not subject:
        return None

    return AuthenticatedPrincipal(
        subject=str(subject),
        email=user.get("email"),
        display_name=user.get("name") or user.get("displayName"),
        session_id=(str(session.get("id")) if session.get("id") else None),
        auth_provider="better-auth",
    )


async def _validate_with_better_auth(
    token: str | None,
    settings: Settings,
    session_cookie: str | None = None,
    session_cookie_name: str | None = None,
    client_ip: str | None = None,
) -> AuthenticatedPrincipal | None:
    if not settings.better_auth_base_url:
        return None

    if token is None and session_cookie is None:
        return None

    endpoint = f"{settings.better_auth_base_url.rstrip('/')}{settings.better_auth_session_path}"
    async with httpx.AsyncClient(timeout=settings.better_auth_timeout_seconds) as client:
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if session_cookie:
            cookie_name = session_cookie_name or settings.better_auth_cookie_name
            headers["Cookie"] = f"{cookie_name}={session_cookie}"
        if client_ip:
            headers["x-real-ip"] = client_ip
        response = await client.get(
            endpoint,
            headers=headers,
        )

    if response.status_code in {
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    }:
        return None
    response.raise_for_status()

    payload = response.json()
    if not isinstance(payload, dict):
        return None

    return _principal_from_better_auth_payload(payload)


def _validate_with_dev_token(token: str, settings: Settings) -> AuthenticatedPrincipal | None:
    if not settings.allow_dev_tokens:
        return None
    if token not in settings.dev_bearer_tokens:
        return None

    token_suffix = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
    return AuthenticatedPrincipal(
        subject=f"dev:{token_suffix}",
        auth_provider="development",
    )


async def require_authenticated_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = _credentials_dependency,
    settings: Settings = _settings_dependency,
) -> AuthenticatedPrincipal:
    if not settings.auth_enabled:
        principal = AuthenticatedPrincipal(
            subject="anonymous-disabled-auth",
            auth_provider="disabled",
        )
        request.state.auth_principal = principal
        return principal

    token = credentials.credentials if credentials is not None else None
    resolved_cookie = extract_better_auth_session_cookie(request, settings.better_auth_cookie_name)
    session_cookie_name, session_cookie = (
        resolved_cookie if resolved_cookie is not None else (None, None)
    )
    if token is None and session_cookie is None:
        raise _unauthorized()

    principal = _validate_with_dev_token(token, settings) if token is not None else None
    if principal is None:
        if not settings.allow_dev_tokens and not settings.better_auth_base_url:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable",
            )
        try:
            principal = await _validate_with_better_auth(
                token,
                settings,
                session_cookie=session_cookie,
                session_cookie_name=session_cookie_name,
                client_ip=request.headers.get("x-real-ip")
                or (request.client.host if request.client else None),
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable",
            ) from exc

    if principal is None:
        raise _unauthorized("Invalid authentication token")

    request.state.auth_principal = principal
    return principal


async def require_internal_key(
    credentials: HTTPAuthorizationCredentials | None = _credentials_dependency,
    settings: Settings = _settings_dependency,
) -> None:
    """Validates the service-to-service bearer token for internal endpoints."""
    if not settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal API not configured",
        )
    token = credentials.credentials if credentials is not None else None
    if not token or token != settings.internal_api_key:
        raise _unauthorized("Invalid internal API key")
