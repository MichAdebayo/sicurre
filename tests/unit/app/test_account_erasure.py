"""The erasure cascade: Cloudflare teardown, workspace rows, then the Better Auth rows.

Direct calls with the runtime query and the teardown route monkeypatched; each test
pins the order of the cascade or the point where it must stop.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from data_platform.api.auth import AuthUser
from data_platform.services import account_erasure
from data_platform.services.account_erasure import erase_account

_USER = AuthUser(
    id="user-1",
    email="owner@example.test",
    display_name="Owner",
    role="owner",
    workspace_id="workspace-1",
    workspace_name="Workspace",
    is_platform_admin=False,
)


def _fragment_query(
    responses: dict[str, list[dict[str, Any]] | Exception],
) -> tuple[list[tuple[str, tuple[Any, ...]]], Any]:
    captured: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        captured.append((sql, params))
        for fragment, response in responses.items():
            if fragment in sql:
                if isinstance(response, Exception):
                    raise response
                return response
        return []

    return captured, query


def _erasure_fixture(
    monkeypatch: pytest.MonkeyPatch,
    integrations: list[dict[str, Any]],
    teardown_error: Exception | None = None,
) -> tuple[list[tuple[str, tuple[Any, ...]]], list[str]]:
    """Wire the erasure route: the integration list answers one SELECT, teardown is recorded."""
    captured, query = _fragment_query(
        {"SELECT id, status FROM cloudflare_integration": integrations}
    )
    monkeypatch.setattr(account_erasure, "execute_runtime_query", query)
    torn_down: list[str] = []

    async def teardown(payload: Any, current_user: AuthUser) -> dict[str, Any]:
        assert current_user is _USER
        if teardown_error is not None:
            raise teardown_error
        torn_down.append(payload.integration_id)
        return {"status": "removed"}

    monkeypatch.setattr(account_erasure, "teardown_cloudflare", teardown)
    return captured, torn_down


@pytest.mark.asyncio
async def test_erasure_waits_for_a_domain_still_provisioning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tearing down a half-provisioned zone would leave Cloudflare resources behind."""
    captured, torn_down = _erasure_fixture(
        monkeypatch,
        [
            {"id": "integration-1", "status": "active"},
            {"id": "integration-2", "status": "provisioning"},
        ],
    )

    with pytest.raises(HTTPException) as excinfo:
        await erase_account(_USER)

    assert excinfo.value.status_code == 409
    assert torn_down == []
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_erasure_tears_every_domain_down_then_deletes_the_workspace_and_the_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cloudflare first, then every workspace table, then the Better Auth rows."""
    captured, torn_down = _erasure_fixture(
        monkeypatch,
        [{"id": "integration-2", "status": "active"}, {"id": "integration-1", "status": "error"}],
    )

    await erase_account(_USER)

    assert torn_down == ["integration-2", "integration-1"]
    deletes = [(sql, params) for sql, params in captured if sql.startswith("DELETE")]
    workspace_deletes = [sql for sql, params in deletes if params == ("workspace-1",)]
    assert workspace_deletes[-1] == "DELETE FROM app_workspace WHERE id = ?"
    assert "DELETE FROM app_workspace_membership WHERE workspace_id = ?" in workspace_deletes
    assert "DELETE FROM app_inference_event WHERE workspace_id = ?" in workspace_deletes
    assert "DELETE FROM app_quarantine_item WHERE workspace_id = ?" in workspace_deletes
    assert "DELETE FROM cloudflare_integration WHERE workspace_id = ?" in workspace_deletes
    # The membership row references the workspace, so it goes before the workspace.
    assert workspace_deletes.index(
        "DELETE FROM app_workspace_membership WHERE workspace_id = ?"
    ) < workspace_deletes.index("DELETE FROM app_workspace WHERE id = ?")
    identity_deletes = deletes[len(workspace_deletes) :]
    assert identity_deletes == [
        ('DELETE FROM "session" WHERE "userId" = ?', ("user-1",)),
        ('DELETE FROM "account" WHERE "userId" = ?', ("user-1",)),
        ('DELETE FROM "verification" WHERE identifier = ?', ("owner@example.test",)),
        ('DELETE FROM "user" WHERE id = ?', ("user-1",)),
    ]


@pytest.mark.asyncio
async def test_a_failed_teardown_stops_the_erasure_before_any_row_is_deleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The member keeps a working account when Cloudflare refuses; nothing is half deleted."""
    captured, torn_down = _erasure_fixture(
        monkeypatch,
        [{"id": "integration-1", "status": "active"}],
        teardown_error=HTTPException(
            status_code=502, detail="Cloudflare could not remove the routing resources"
        ),
    )

    with pytest.raises(HTTPException) as excinfo:
        await erase_account(_USER)

    assert excinfo.value.status_code == 502
    assert torn_down == []
    assert [sql for sql, _ in captured if sql.startswith("DELETE")] == []


@pytest.mark.asyncio
async def test_a_member_without_a_workspace_loses_only_the_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Signed up but never loaded the app: there is no workspace row to delete."""
    captured, torn_down = _erasure_fixture(monkeypatch, [])
    orphan = AuthUser(
        id="user-9",
        email="new@example.test",
        display_name="New",
        role="owner",
        workspace_id="",
        workspace_name="",
        is_platform_admin=False,
    )

    await erase_account(orphan)

    assert torn_down == []
    assert [sql for sql, _ in captured] == [
        'DELETE FROM "session" WHERE "userId" = ?',
        'DELETE FROM "account" WHERE "userId" = ?',
        'DELETE FROM "verification" WHERE identifier = ?',
        'DELETE FROM "user" WHERE id = ?',
    ]


def _erasure_with_copies(
    monkeypatch: pytest.MonkeyPatch,
    copies: list[str],
    delete_error: Exception | None = None,
) -> tuple[list[tuple[str, tuple[Any, ...]]], list[str], list[str]]:
    """Wire an erasure whose workspace holds stored quarantine copies."""
    captured, query = _fragment_query(
        {
            "SELECT id, status FROM cloudflare_integration": [{"id": "integration-1", "status": "active"}],
            "SELECT raw_storage_uri FROM app_quarantine_item": [
                {"raw_storage_uri": uri} for uri in copies
            ],
        }
    )
    monkeypatch.setattr(account_erasure, "execute_runtime_query", query)
    events: list[str] = []
    dropped: list[str] = []

    async def teardown(payload: Any, current_user: AuthUser) -> dict[str, Any]:
        events.append("teardown")
        return {"status": "removed"}

    class Store:
        async def delete(self, storage_uri: str) -> None:
            # Nothing may be deleted from the database before the copies are gone.
            assert not any(sql.startswith("DELETE") for sql, _ in captured)
            if delete_error is not None:
                raise delete_error
            events.append("copy")
            dropped.append(storage_uri)

    monkeypatch.setattr(account_erasure, "teardown_cloudflare", teardown)
    monkeypatch.setattr(account_erasure, "get_settings", lambda: object())
    monkeypatch.setattr(account_erasure, "build_quarantine_store", lambda _settings: Store())
    return captured, events, dropped


@pytest.mark.asyncio
async def test_erasure_deletes_every_stored_quarantine_copy_before_any_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deleting the rows alone left the raw messages in storage for up to 14 days."""
    captured, events, dropped = _erasure_with_copies(
        monkeypatch, ["r2://quarantine/workspace-1/a.eml", "r2://quarantine/workspace-1/b.eml"]
    )

    await erase_account(_USER)

    assert dropped == ["r2://quarantine/workspace-1/a.eml", "r2://quarantine/workspace-1/b.eml"]
    assert events == ["teardown", "copy", "copy"], "Cloudflare first, then the copies"
    assert "DELETE FROM app_quarantine_item WHERE workspace_id = ?" in [sql for sql, _ in captured]


@pytest.mark.asyncio
async def test_a_storage_failure_stops_the_erasure_before_any_row_is_deleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rows keep pointing at the copies, so a retry can finish the job."""
    captured, _events, dropped = _erasure_with_copies(
        monkeypatch, ["r2://quarantine/workspace-1/a.eml"], delete_error=RuntimeError("R2 unreachable")
    )

    with pytest.raises(HTTPException) as excinfo:
        await erase_account(_USER)

    assert excinfo.value.status_code == 503
    assert dropped == []
    assert [sql for sql, _ in captured if sql.startswith("DELETE")] == []


@pytest.mark.asyncio
async def test_an_erasure_without_stored_copies_never_opens_the_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured, events, dropped = _erasure_with_copies(monkeypatch, [])
    monkeypatch.setattr(
        account_erasure,
        "build_quarantine_store",
        lambda _settings: pytest.fail("the store was opened with nothing to delete"),
    )

    await erase_account(_USER)

    assert dropped == [] and events == ["teardown"]
