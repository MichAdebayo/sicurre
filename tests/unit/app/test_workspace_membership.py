"""The workspace bootstrap that runs on every authenticated request.

``async_query`` is replaced by a recorder so each test pins which statements a
request issues: creating the workspace on first sight, and what an existing
member's request writes.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from core.config import Settings
from core.security import AuthenticatedPrincipal
from data_platform.api import auth as app_auth

PRINCIPAL = AuthenticatedPrincipal(
    subject="user-1",
    email="Owner@Example.test",
    display_name="Owner",
    auth_provider="better-auth",
)


def _recorder(
    monkeypatch: pytest.MonkeyPatch, membership: list[dict[str, Any]]
) -> list[tuple[str, tuple[Any, ...]]]:
    captured: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        captured.append((" ".join(sql.split()), params))
        if "FROM app_workspace_membership m" in sql:
            return membership
        return []

    monkeypatch.setattr(app_auth, "async_query", query)
    monkeypatch.setattr(app_auth, "ensure_runtime_tables", lambda: None)
    monkeypatch.setattr(
        app_auth,
        "get_settings",
        lambda: Settings(_env_file=None, platform_admin_emails="owner@example.test"),
    )
    return captured


def _writes(captured: list[tuple[str, tuple[Any, ...]]]) -> list[str]:
    return [sql for sql, _ in captured if sql.startswith(("INSERT", "UPDATE", "DELETE"))]


@pytest.mark.asyncio
async def test_a_first_request_creates_the_workspace_and_owner_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _recorder(monkeypatch, membership=[])

    user = await app_auth._ensure_workspace_membership(PRINCIPAL)

    writes = _writes(captured)
    assert writes[0].startswith("INSERT INTO app_workspace (")
    assert writes[1].startswith("INSERT INTO app_workspace_membership (")
    workspace_params = next(p for s, p in captured if s.startswith("INSERT INTO app_workspace ("))
    assert workspace_params[1:4] == ("Owner Workspace", "owner-user-1", "user-1")
    assert user.email == "owner@example.test"
    assert user.role == "owner"
    assert user.workspace_name == "Owner Workspace"
    assert user.workspace_id == workspace_params[0]
    assert user.is_platform_admin is True


@pytest.mark.asyncio
async def test_a_first_request_adopts_rows_recorded_before_the_workspace_existed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _recorder(monkeypatch, membership=[])

    user = await app_auth._ensure_workspace_membership(PRINCIPAL)

    backfills = [(s, p) for s, p in captured if "(workspace_id IS NULL OR workspace_id = '')" in s]
    assert [s.split(" SET ")[0] for s, _ in backfills] == [
        "UPDATE app_inference_event",
        "UPDATE cloudflare_integration",
    ]
    assert all(p == (user.workspace_id, "user-1", "owner@example.test") for _, p in backfills)


@pytest.mark.asyncio
async def test_a_request_without_an_email_is_refused_before_any_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _recorder(monkeypatch, membership=[])
    nameless = AuthenticatedPrincipal(subject="user-1", auth_provider="better-auth")

    with pytest.raises(HTTPException) as excinfo:
        await app_auth._ensure_workspace_membership(nameless)

    assert excinfo.value.status_code == 401
    assert captured == []


_EXISTING = {
    "workspace_id": "ws-1",
    "membership_role": "owner",
    "workspace_name": "Owner Workspace",
    "member_email": "owner@example.test",
    "member_display_name": "Owner",
}


@pytest.mark.asyncio
async def test_an_existing_member_request_reads_once_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The common case: no update and no backfill on a request that changes nothing."""
    captured = _recorder(monkeypatch, membership=[dict(_EXISTING)])

    user = await app_auth._ensure_workspace_membership(PRINCIPAL)

    assert _writes(captured) == []
    assert len(captured) == 1
    assert (user.workspace_id, user.role, user.workspace_name) == (
        "ws-1",
        "owner",
        "Owner Workspace",
    )


@pytest.mark.asyncio
async def test_an_existing_member_with_a_new_name_is_updated_once_without_a_backfill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _recorder(monkeypatch, membership=[{**_EXISTING, "member_display_name": "Old name"}])

    await app_auth._ensure_workspace_membership(PRINCIPAL)

    assert _writes(captured) == [
        "UPDATE app_workspace_membership SET email = ?, display_name = ?, updated_at = ? WHERE auth_user_id = ?"
    ]
    params = next(p for s, p in captured if s.startswith("UPDATE app_workspace_membership"))
    assert (params[0], params[1], params[3]) == ("owner@example.test", "Owner", "user-1")


@pytest.mark.asyncio
async def test_an_existing_member_with_a_new_address_is_updated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _recorder(
        monkeypatch, membership=[{**_EXISTING, "member_email": "old@example.test"}]
    )

    await app_auth._ensure_workspace_membership(PRINCIPAL)

    assert len(_writes(captured)) == 1
