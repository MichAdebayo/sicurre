"""Token check, stored token and the query seam: the refusal paths."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from data_platform.api.auth import AuthUser
from data_platform.api.routers import cloudflare_account
from data_platform.api.routers.cloudflare_account import (
    CloudflareTokenSaveRequest,
    TokenVerifyRequest,
    get_workspace_cloudflare_token,
    save_workspace_cloudflare_token,
    verify_cloudflare_token,
)
from data_platform.services.cloudflare_provisioner import CloudflareAPIError


def _user() -> AuthUser:
    return AuthUser(
        id="user-1",
        email="owner@example.test",
        display_name="Owner",
        role="owner",
        workspace_id="workspace-1",
        workspace_name="Workspace",
        is_platform_admin=False,
    )


class _Provisioner:
    def __init__(self, api_token: str, *, valid: bool = True, error: str | None = None) -> None:
        self.valid = valid
        self.error = error

    async def verify_token(self) -> bool:
        return self.valid

    async def get_zone(self, _zone_name: str) -> tuple[str, str]:
        if self.error:
            raise CloudflareAPIError(self.error)
        return "zone-1", "account-1"


def _provisioner(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> None:
    monkeypatch.setattr(
        cloudflare_account,
        "CloudflareProvisioner",
        lambda api_token: _Provisioner(api_token, **kwargs),
    )


@pytest.mark.asyncio
async def test_a_token_cloudflare_rejects_is_reported_not_raised(monkeypatch) -> None:
    _provisioner(monkeypatch, valid=False)
    result = await verify_cloudflare_token(
        TokenVerifyRequest(cf_api_token="t", zone_name="sicurre.com"), _user()
    )
    assert result == {"valid": False, "error": "Token verification failed"}


@pytest.mark.asyncio
async def test_a_zone_the_token_cannot_see_is_reported_with_cloudflares_reason(monkeypatch) -> None:
    _provisioner(monkeypatch, error="Zone not found")
    result = await verify_cloudflare_token(
        TokenVerifyRequest(cf_api_token="t", zone_name="sicurre.com"), _user()
    )
    assert result == {"valid": False, "error": "Zone not found"}


@pytest.mark.asyncio
async def test_token_status_falls_back_to_the_integration_token(monkeypatch) -> None:
    """A domain connected with a token, but no workspace-level copy, still counts as configured."""

    async def query(sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if "FROM cloudflare_integration" in sql:
            return [{"api_token": "enc:v1:ciphertext"}]
        return []

    monkeypatch.setattr(cloudflare_account, "ensure_runtime_tables", lambda: None)
    monkeypatch.setattr(cloudflare_account, "_async_query", query)

    assert await get_workspace_cloudflare_token(_user()) == {"configured": True}


@pytest.mark.asyncio
async def test_saving_a_rejected_token_writes_nothing(monkeypatch) -> None:
    writes: list[str] = []

    async def query(sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        writes.append(sql)
        return []

    monkeypatch.setattr(cloudflare_account, "_async_query", query)

    _provisioner(monkeypatch, valid=False)
    with pytest.raises(HTTPException) as rejected:
        await save_workspace_cloudflare_token(CloudflareTokenSaveRequest(cf_api_token="t"), _user())

    class Failing(_Provisioner):
        async def verify_token(self) -> bool:
            raise CloudflareAPIError("Cloudflare is unreachable")

    monkeypatch.setattr(
        cloudflare_account, "CloudflareProvisioner", lambda api_token: Failing(api_token)
    )
    with pytest.raises(HTTPException) as unreachable:
        await save_workspace_cloudflare_token(CloudflareTokenSaveRequest(cf_api_token="t"), _user())

    assert (rejected.value.status_code, unreachable.value.status_code) == (400, 400)
    assert "Cloudflare is unreachable" in unreachable.value.detail
    assert writes == []


@pytest.mark.asyncio
async def test_the_query_seam_delegates_to_the_runtime_engine(monkeypatch) -> None:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    async def engine(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        calls.append((sql, params))
        return [{"ok": 1}]

    monkeypatch.setattr(cloudflare_account, "execute_runtime_query", engine)
    assert await cloudflare_account._async_query("SELECT 1", (1,)) == [{"ok": 1}]
    assert calls == [("SELECT 1", (1,))]
