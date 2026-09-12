"""Direct coverage of the quarantine listing, release, deletion and whitelist routes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from data_platform.api import workspace_scope
from data_platform.api.auth import AuthUser
from data_platform.api.routers import quarantine
from data_platform.services.quarantine_delivery import QuarantineDeliveryError

RAW_URI = "file:///quarantine/held-1.eml"
INTEGRATION = {
    "account_id": "account-1",
    "zone_id": "zone-1",
    "zone_name": "example.test",
    "destination_email": "owner@example.test",
    "api_token": "encrypted-token",
}


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


async def _allow(_domain: str, _workspace_id: str) -> None:
    return None


def _held_item(**overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": "held-1",
        "status": "held",
        "raw_storage_uri": RAW_URI,
        "message_id": "event-1",
        "domain": "example.test",
        "sender": " Billing@Example.NET ",
        "safety_verdict": "phishing",
        "delivery_message_id": None,
    }
    item.update(overrides)
    return item


class _FakeDb:
    """Answer SQL by fragment while recording every statement in order."""

    def __init__(self, *handlers: tuple[str, Any]) -> None:
        self.handlers = list(handlers)
        self.queries: list[tuple[str, tuple[Any, ...]]] = []

    async def __call__(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        self.queries.append((sql, params))
        for fragment, rows in self.handlers:
            if fragment in sql:
                if isinstance(rows, Exception):
                    raise rows
                return list(rows)
        return []

    def sql_containing(self, fragment: str) -> list[str]:
        return [sql for sql, _ in self.queries if fragment in sql]


class _Store:
    def __init__(
        self, *, read_error: Exception | None = None, delete_error: Exception | None = None
    ):
        self.read_error = read_error
        self.delete_error = delete_error
        self.deleted: list[str] = []

    async def read(self, uri: str) -> bytes:
        if self.read_error is not None:
            raise self.read_error
        assert uri == RAW_URI
        return b"From: sender@example.net\r\n\r\nOriginal"

    async def delete(self, uri: str) -> None:
        if self.delete_error is not None:
            raise self.delete_error
        self.deleted.append(uri)


def _install_delivery(
    monkeypatch: pytest.MonkeyPatch,
    *,
    store: _Store,
    send_error: Exception | None = None,
) -> dict[str, Any]:
    """Patch the delivery collaborators and return the captured send kwargs."""
    captured: dict[str, Any] = {}

    async def sending_address(**_kwargs: Any) -> str:
        return "quarantine@example.test"

    async def deliver(**kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        if send_error is not None:
            raise send_error
        return SimpleNamespace(message_id="delivery-1", recipient="owner@example.test", queued=True)

    monkeypatch.setattr(workspace_scope, "require_workspace_domain", _allow)
    monkeypatch.setattr(
        quarantine,
        "get_settings",
        lambda: SimpleNamespace(secret_encryption_key=None, environment="test"),
    )
    monkeypatch.setattr(quarantine, "build_quarantine_store", lambda _settings: store)
    monkeypatch.setattr(quarantine, "decrypt_secret", lambda value, **_kwargs: f"plain:{value}")
    monkeypatch.setattr(quarantine, "resolve_sending_address", sending_address)
    monkeypatch.setattr(
        quarantine,
        "prepare_restoration_mime",
        lambda raw, *, sender, recipient: raw + f"\r\n[{sender}->{recipient}]".encode(),
    )
    monkeypatch.setattr(quarantine, "send_raw_email", deliver)
    return captured


def _release_db(
    item: dict[str, Any],
    *,
    integrations: list[dict[str, Any]] | None = None,
    claimed: list[dict[str, Any]] | None = None,
) -> _FakeDb:
    return _FakeDb(
        ("SELECT * FROM app_quarantine_item", [item]),
        ("SELECT account_id", [INTEGRATION] if integrations is None else integrations),
        ("RETURNING id", [{"id": item["id"]}] if claimed is None else claimed),
    )


@pytest.mark.asyncio
async def test_list_quarantine_returns_only_the_held_items_of_the_owned_domain(monkeypatch):
    """The listing purges expired items first and projects each held row."""
    purged: list[str] = []

    async def purge(workspace_id: str) -> None:
        purged.append(workspace_id)

    row = {
        "id": "held-1",
        "message_id": "event-1",
        "sender": "sender@example.net",
        "subject": "Invoice",
        "body_text": "Pay now",
        "safety_verdict": "phishing",
        "composite_score": 0.91,
        "status": "held",
        "created_at": "2026-09-01T00:00:00+00:00",
        "expires_at": "2026-09-08T00:00:00+00:00",
        "raw_storage_uri": RAW_URI,
    }
    db = _FakeDb(("SELECT * FROM app_quarantine_item", [row]))
    monkeypatch.setattr(workspace_scope, "require_workspace_domain", _allow)
    monkeypatch.setattr(quarantine, "_purge_expired_quarantine", purge)
    monkeypatch.setattr(quarantine, "execute_runtime_query", db)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", db)

    items = await quarantine.list_quarantine("Example.TEST", _user())

    assert purged == ["workspace-1"]
    assert items == [
        {
            "id": "held-1",
            "domain": "example.test",
            "message_id": "event-1",
            "sender": "sender@example.net",
            "subject": "Invoice",
            "body_text": "Pay now",
            "safety_verdict": "phishing",
            "composite_score": 0.91,
            "status": "held",
            "created_at": "2026-09-01T00:00:00+00:00",
            "expires_at": "2026-09-08T00:00:00+00:00",
        }
    ]
    assert "status = 'held'" in db.queries[0][0]
    assert db.queries[0][1] == ("workspace-1", "example.test")


@pytest.mark.asyncio
async def test_release_returns_404_when_the_item_is_not_in_the_workspace(monkeypatch):
    """An unknown or foreign item is reported as missing, never as released."""
    db = _FakeDb()
    monkeypatch.setattr(workspace_scope, "require_workspace_domain", _allow)
    monkeypatch.setattr(quarantine, "execute_runtime_query", db)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", db)

    with pytest.raises(HTTPException) as exc_info:
        await quarantine.release_quarantine_item("missing", "example.test", _user())

    assert exc_info.value.status_code == 404
    assert len(db.queries) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("integrations", "expected_forwarded_to"),
    [
        ([{"destination_email": "owner@example.test"}], "owner@example.test"),
        ([], ""),
    ],
)
async def test_release_of_an_already_released_item_is_idempotent(
    monkeypatch, integrations: list[dict[str, Any]], expected_forwarded_to: str
):
    """A second release replays the stored delivery instead of sending again."""
    item = _held_item(status="released", delivery_message_id="delivery-0")
    db = _FakeDb(
        ("SELECT * FROM app_quarantine_item", [item]),
        ("SELECT destination_email FROM cloudflare_integration", integrations),
    )
    sent: list[dict[str, Any]] = []

    async def deliver(**kwargs: Any) -> None:
        sent.append(kwargs)

    monkeypatch.setattr(workspace_scope, "require_workspace_domain", _allow)
    monkeypatch.setattr(quarantine, "execute_runtime_query", db)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", db)
    monkeypatch.setattr(quarantine, "send_raw_email", deliver)

    response = await quarantine.release_quarantine_item("held-1", "example.test", _user())

    assert response == {
        "status": "released",
        "forwarded_to": expected_forwarded_to,
        "delivery_message_id": "delivery-0",
        "idempotent": True,
    }
    assert sent == []
    assert db.sql_containing("UPDATE") == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("item", "integrations", "claimed", "expected_detail"),
    [
        pytest.param(
            _held_item(status="releasing"),
            None,
            None,
            "Message release is already in progress",
            id="releasing",
        ),
        pytest.param(
            _held_item(status="deleted"),
            None,
            None,
            "Message is no longer held",
            id="deleted",
        ),
        pytest.param(
            _held_item(raw_storage_uri=None),
            None,
            None,
            "Original email content is unavailable; the message was not released",
            id="no-raw-content",
        ),
        pytest.param(
            _held_item(),
            [],
            None,
            "Active Cloudflare integration required",
            id="no-active-integration",
        ),
        pytest.param(
            _held_item(),
            [{**INTEGRATION, "api_token": None}],
            None,
            "Cloudflare token is not configured",
            id="integration-without-token",
        ),
        pytest.param(
            _held_item(),
            None,
            [],
            "Message release is already in progress",
            id="claim-lost-to-concurrent-release",
        ),
    ],
)
async def test_release_refuses_with_409_before_any_delivery_attempt(
    monkeypatch,
    item: dict[str, Any],
    integrations: list[dict[str, Any]] | None,
    claimed: list[dict[str, Any]] | None,
    expected_detail: str,
):
    """Every precondition failure is a 409 and nothing is read or sent."""
    store = _Store()
    captured = _install_delivery(monkeypatch, store=store)
    db = _release_db(item, integrations=integrations, claimed=claimed)
    monkeypatch.setattr(quarantine, "execute_runtime_query", db)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", db)

    with pytest.raises(HTTPException) as exc_info:
        await quarantine.release_quarantine_item("held-1", "example.test", _user())

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == expected_detail
    assert captured == {}
    assert store.deleted == []
    assert db.sql_containing("status = 'released'") == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "expected_status"),
    [
        ("cloudflare_permission_required", 403),
        ("cloudflare_send_failed", 424),
    ],
)
async def test_release_puts_the_item_back_on_hold_when_delivery_is_refused(
    monkeypatch, code: str, expected_status: int
):
    """A delivery error keeps the item held with the provider message recorded."""
    error = QuarantineDeliveryError(code, "Cloudflare refused the send")
    store = _Store()
    _install_delivery(monkeypatch, store=store, send_error=error)
    db = _release_db(_held_item())
    monkeypatch.setattr(quarantine, "execute_runtime_query", db)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", db)

    with pytest.raises(HTTPException) as exc_info:
        await quarantine.release_quarantine_item("held-1", "example.test", _user())

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == "Cloudflare refused the send"
    assert exc_info.value.__cause__ is error
    reset_sql, reset_params = db.queries[-1]
    assert "SET status = 'held', last_delivery_error = ?" in reset_sql
    assert reset_params == ("Cloudflare refused the send", "held-1", "workspace-1", "example.test")
    assert store.deleted == []
    assert db.sql_containing("status = 'released'") == []


@pytest.mark.asyncio
async def test_release_reports_storage_unavailable_on_an_unexpected_failure(monkeypatch):
    """A raw-store failure is mapped to 503 and the item returns to held."""
    store = _Store(read_error=RuntimeError("R2 unavailable"))
    captured = _install_delivery(monkeypatch, store=store)
    db = _release_db(_held_item())
    monkeypatch.setattr(quarantine, "execute_runtime_query", db)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", db)

    with pytest.raises(HTTPException) as exc_info:
        await quarantine.release_quarantine_item("held-1", "example.test", _user())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Quarantine storage is temporarily unavailable"
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    reset_sql, reset_params = db.queries[-1]
    assert "SET status = 'held', last_delivery_error = ?" in reset_sql
    assert reset_params[0] == "Quarantine storage is unavailable"
    assert captured == {}


@pytest.mark.asyncio
async def test_release_delivers_records_feedback_and_clears_raw_custody(monkeypatch):
    """A successful release claims, sends the restored MIME, then drops the raw copy."""
    store = _Store()
    captured = _install_delivery(monkeypatch, store=store)
    db = _release_db(_held_item())
    monkeypatch.setattr(quarantine, "execute_runtime_query", db)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", db)

    response = await quarantine.release_quarantine_item("held-1", "example.test", _user())

    assert response == {
        "status": "released",
        "forwarded_to": "owner@example.test",
        "delivery_message_id": "delivery-1",
        "queued": True,
        "idempotent": False,
    }
    assert captured["api_token"] == "plain:encrypted-token"
    assert captured["envelope_from"] == "quarantine@example.test"
    assert captured["recipient"] == "owner@example.test"
    assert captured["raw_mime"].endswith(b"[quarantine@example.test->owner@example.test]")
    claim_sql = db.sql_containing("RETURNING id")
    assert len(claim_sql) == 1 and "status = 'releasing'" in claim_sql[0]
    released = [params for sql, params in db.queries if "status = 'released'" in sql]
    assert released == [("delivery-1", released[0][1], "held-1", "workspace-1", "example.test")]
    feedback = [params for sql, params in db.queries if "INSERT INTO app_feedback" in sql]
    assert len(feedback) == 1
    assert feedback[0][1:5] == ("workspace-1", "user-1", "event-1", "phishing")
    assert store.deleted == [RAW_URI]
    assert len(db.sql_containing("SET raw_storage_uri = NULL")) == 1


@pytest.mark.asyncio
async def test_release_still_succeeds_when_the_raw_copy_cannot_be_deleted(monkeypatch):
    """Failing to drop the raw copy after delivery is suppressed, not surfaced."""
    store = _Store(delete_error=RuntimeError("R2 unavailable"))
    _install_delivery(monkeypatch, store=store)
    db = _release_db(_held_item())
    monkeypatch.setattr(quarantine, "execute_runtime_query", db)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", db)

    response = await quarantine.release_quarantine_item("held-1", "example.test", _user())

    assert response["status"] == "released"
    assert response["idempotent"] is False
    assert store.deleted == []
    assert len(db.sql_containing("status = 'released'")) == 1
    assert db.sql_containing("SET raw_storage_uri = NULL") == []


@pytest.mark.asyncio
async def test_release_feedback_failure_is_swallowed(monkeypatch):
    """The false-positive record is best effort and never blocks the release."""
    db = _FakeDb(("INSERT INTO app_feedback", RuntimeError("feedback table missing")))
    monkeypatch.setattr(quarantine, "execute_runtime_query", db)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", db)

    await quarantine._record_release_feedback(item=_held_item(), current_user=_user())

    assert len(db.queries) == 1
    assert db.queries[0][1][1:4] == ("workspace-1", "user-1", "event-1")


@pytest.mark.asyncio
async def test_delete_returns_404_when_the_item_is_not_in_the_workspace(monkeypatch):
    """Deletion of an unknown item does not touch the store or the row."""
    db = _FakeDb()
    monkeypatch.setattr(workspace_scope, "require_workspace_domain", _allow)
    monkeypatch.setattr(quarantine, "execute_runtime_query", db)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", db)

    with pytest.raises(HTTPException) as exc_info:
        await quarantine.delete_quarantine_item("missing", "example.test", _user())

    assert exc_info.value.status_code == 404
    assert len(db.queries) == 1


@pytest.mark.asyncio
async def test_delete_skips_the_store_when_no_raw_copy_is_held(monkeypatch):
    """A preview-only record is scrubbed without contacting raw storage."""
    db = _FakeDb(("SELECT raw_storage_uri", [{"raw_storage_uri": None}]))
    monkeypatch.setattr(workspace_scope, "require_workspace_domain", _allow)
    monkeypatch.setattr(quarantine, "execute_runtime_query", db)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", db)
    monkeypatch.setattr(
        quarantine, "build_quarantine_store", lambda _settings: pytest.fail("store built")
    )

    assert await quarantine.delete_quarantine_item("held-1", "example.test", _user()) == {
        "status": "deleted"
    }
    assert len(db.sql_containing("status = 'deleted'")) == 1


@pytest.mark.asyncio
async def test_delete_drops_the_raw_copy_before_scrubbing_the_row(monkeypatch):
    """The raw object is removed from custody first, then the row is redacted."""
    store = _Store()
    db = _FakeDb(("SELECT raw_storage_uri", [{"raw_storage_uri": RAW_URI}]))
    monkeypatch.setattr(workspace_scope, "require_workspace_domain", _allow)
    monkeypatch.setattr(quarantine, "execute_runtime_query", db)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", db)
    monkeypatch.setattr(quarantine, "get_settings", lambda: SimpleNamespace(environment="test"))
    monkeypatch.setattr(quarantine, "build_quarantine_store", lambda _settings: store)

    assert await quarantine.delete_quarantine_item("held-1", "example.test", _user()) == {
        "status": "deleted"
    }
    assert store.deleted == [RAW_URI]
    scrub_sql, scrub_params = db.queries[-1]
    assert "raw_storage_uri = NULL" in scrub_sql
    assert scrub_params == ("held-1", "workspace-1", "example.test")


@pytest.mark.asyncio
async def test_delete_reports_storage_unavailable_when_the_raw_copy_cannot_be_dropped(
    monkeypatch,
):
    """A store failure surfaces as 503 and the row keeps its raw pointer."""
    store = _Store(delete_error=RuntimeError("R2 unavailable"))
    db = _FakeDb(("SELECT raw_storage_uri", [{"raw_storage_uri": RAW_URI}]))
    monkeypatch.setattr(workspace_scope, "require_workspace_domain", _allow)
    monkeypatch.setattr(quarantine, "execute_runtime_query", db)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", db)
    monkeypatch.setattr(quarantine, "get_settings", lambda: SimpleNamespace(environment="test"))
    monkeypatch.setattr(quarantine, "build_quarantine_store", lambda _settings: store)

    with pytest.raises(HTTPException) as exc_info:
        await quarantine.delete_quarantine_item("held-1", "example.test", _user())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Quarantine storage is temporarily unavailable"
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert db.sql_containing("status = 'deleted'") == []


@pytest.mark.asyncio
async def test_whitelist_returns_404_when_no_held_or_released_item_matches(monkeypatch):
    """The whitelist route refuses before releasing or writing any rule."""
    db = _FakeDb()
    called: list[str] = []

    async def release(**kwargs: Any) -> dict[str, Any]:
        called.append(kwargs["id"])
        return {}

    monkeypatch.setattr(workspace_scope, "require_workspace_domain", _allow)
    monkeypatch.setattr(quarantine, "execute_runtime_query", db)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", db)
    monkeypatch.setattr(quarantine, "_release_quarantine_item", release)

    with pytest.raises(HTTPException) as exc_info:
        await quarantine.release_and_whitelist_item("missing", "example.test", _user())

    assert exc_info.value.status_code == 404
    assert called == []
    assert db.sql_containing("INSERT") == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("existing_rules", "expected_inserts"),
    [
        ([], 1),
        ([{"id": "rule-1"}], 0),
    ],
)
async def test_whitelist_releases_then_adds_the_sender_rule_once(
    monkeypatch, existing_rules: list[dict[str, Any]], expected_inserts: int
):
    """The release result is returned with the normalized pattern that was allowed."""
    db = _FakeDb(
        ("SELECT * FROM app_quarantine_item", [_held_item()]),
        ("SELECT id FROM app_security_rule", existing_rules),
    )
    release_calls: list[dict[str, Any]] = []

    async def release(**kwargs: Any) -> dict[str, Any]:
        release_calls.append(kwargs)
        return {
            "status": "released",
            "forwarded_to": "owner@example.test",
            "delivery_message_id": "delivery-1",
            "queued": False,
            "idempotent": False,
        }

    monkeypatch.setattr(workspace_scope, "require_workspace_domain", _allow)
    monkeypatch.setattr(quarantine, "execute_runtime_query", db)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", db)
    monkeypatch.setattr(quarantine, "_release_quarantine_item", release)

    response = await quarantine.release_and_whitelist_item("held-1", "Example.TEST", _user())

    assert response == {
        "status": "released",
        "forwarded_to": "owner@example.test",
        "delivery_message_id": "delivery-1",
        "queued": False,
        "idempotent": False,
        "whitelisted_pattern": "billing@example.net",
    }
    assert release_calls == [{"id": "held-1", "domain": "example.test", "current_user": _user()}]
    lookup_params = [params for sql, params in db.queries if "app_security_rule WHERE" in sql]
    assert lookup_params == [("workspace-1", "example.test", "billing@example.net")]
    inserts = [params for sql, params in db.queries if "INSERT INTO app_security_rule" in sql]
    assert len(inserts) == expected_inserts
    if inserts:
        assert inserts[0][1:4] == ("workspace-1", "example.test", "billing@example.net")
