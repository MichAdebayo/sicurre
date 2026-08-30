"""Background Domain Shield monitoring contracts."""

from __future__ import annotations

from typing import Any

import pytest

from data_platform.cron_schedulers.app import run_domain_shield_monitor as monitor


@pytest.mark.asyncio
async def test_monitor_refreshes_every_active_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Browser selection must not determine which connected domains are monitored."""
    rows = [
        {
            "workspace_id": "workspace-1",
            "domain": "vinse.app",
            "auth_user_id": "user-1",
            "email": "owner@example.test",
            "display_name": "Owner",
            "role": "owner",
            "workspace_name": "Workspace",
        },
        {
            "workspace_id": "workspace-1",
            "domain": "sicurre.com",
            "auth_user_id": "user-1",
            "email": "owner@example.test",
            "display_name": "Owner",
            "role": "owner",
            "workspace_name": "Workspace",
        },
    ]
    refreshed: list[tuple[str, str, bool]] = []

    async def query(_sql: str) -> list[dict[str, Any]]:
        return rows

    async def refresh(*, domain: str, refresh: bool, current_user: Any) -> None:
        refreshed.append((current_user.workspace_id, domain, refresh))

    monkeypatch.setattr(monitor, "async_query", query)
    monkeypatch.setattr(monitor, "check_domain_shield_status", refresh)

    await monitor.main()

    assert refreshed == [
        ("workspace-1", "vinse.app", True),
        ("workspace-1", "sicurre.com", True),
    ]


@pytest.mark.asyncio
async def test_monitor_attempts_remaining_domains_before_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One provider failure cannot prevent later domains from being inspected."""
    rows = [
        {
            "workspace_id": "workspace-1",
            "domain": domain,
            "auth_user_id": "user-1",
            "email": "owner@example.test",
            "display_name": "Owner",
            "role": "owner",
            "workspace_name": "Workspace",
        }
        for domain in ("broken.test", "healthy.test")
    ]
    attempted: list[str] = []

    async def query(_sql: str) -> list[dict[str, Any]]:
        return rows

    async def refresh(*, domain: str, **_kwargs: Any) -> None:
        attempted.append(domain)
        if domain == "broken.test":
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(monitor, "async_query", query)
    monkeypatch.setattr(monitor, "check_domain_shield_status", refresh)

    with pytest.raises(RuntimeError, match="1 domain"):
        await monitor.main()

    assert attempted == ["broken.test", "healthy.test"]
