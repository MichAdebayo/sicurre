"""Platform capabilities must not replace customer onboarding or tenant scope."""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from data_platform.api.auth import AuthUser
from data_platform.api.routers import app_routes


def _user(platform_admin: bool) -> AuthUser:
    return AuthUser(
        id="owner-1",
        email="michael@sicurre.com",
        display_name="Michael",
        role="owner",
        workspace_id="own-workspace",
        workspace_name="Michael's workspace",
        is_platform_admin=platform_admin,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("platform_admin", [False, True])
@pytest.mark.parametrize(
    ("has_integration", "threat_count", "onboarding"),
    [(False, 0, True), (True, 0, False), (False, 4, False)],
)
async def test_admin_and_customer_use_the_same_workspace_onboarding(
    monkeypatch: pytest.MonkeyPatch,
    platform_admin: bool,
    has_integration: bool,
    threat_count: int,
    onboarding: bool,
) -> None:
    """Admin capability is retained without exempting a new workspace from setup."""
    count = AsyncMock(return_value=threat_count)
    connected = AsyncMock(return_value=has_integration)
    monkeypatch.setattr(app_routes, "_workspace_threat_count", count)
    monkeypatch.setattr(app_routes, "_workspace_has_cloudflare_integration", connected)

    result = await app_routes.get_session(_user(platform_admin))

    assert result["onboarding_required"] is onboarding
    assert result["is_platform_admin"] is platform_admin
    assert result["role"] == "owner"
    assert result["workspace_id"] == "own-workspace"
    count.assert_awaited_once_with("own-workspace")
    connected.assert_awaited_once_with("own-workspace")


@pytest.mark.asyncio
@pytest.mark.parametrize("platform_admin", [False, True])
@pytest.mark.parametrize(
    "endpoint",
    [
        app_routes.get_threats,
        app_routes.list_quarantine,
        app_routes.list_alert_history,
        app_routes.get_alert_preferences,
        app_routes.get_dmarc_report_summary,
    ],
)
async def test_customer_routes_reject_foreign_domains_even_for_platform_admins(
    monkeypatch: pytest.MonkeyPatch, platform_admin: bool, endpoint: Any
) -> None:
    """The actual domain ownership check applies before accessing any mailbox data."""
    query = AsyncMock(return_value=[])
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    with pytest.raises(HTTPException) as error:
        await endpoint(domain="foreign.test", current_user=_user(platform_admin))

    assert error.value.status_code == 404
    assert query.call_count == 1
    assert query.call_args.args[1] == ("own-workspace", "foreign.test")


@pytest.mark.asyncio
async def test_admin_customer_kpis_never_include_global_training_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Customer KPI data remains domain-scoped regardless of platform privilege."""
    captured: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        captured.append((sql, params))
        if "SELECT 1 FROM cloudflare_integration" in sql:
            return [{"found": 1}]
        return [{"label_verdict": "legitimate", "cnt": 2}]

    monkeypatch.setattr(app_routes, "async_query_auth_db", query)
    count = AsyncMock(return_value=2)
    monkeypatch.setattr(app_routes, "_workspace_threat_count", count)
    session = AsyncMock()

    result = await app_routes.get_kpis("own.test", session, _user(True))

    assert result["threats_legitimate_count"] == 2
    assert result["dataset_items_count"] == 0
    count.assert_awaited_once_with("own-workspace", "own.test")
    session.execute.assert_not_awaited()
    assert all(params == ("own-workspace", "own.test") for _, params in captured)
