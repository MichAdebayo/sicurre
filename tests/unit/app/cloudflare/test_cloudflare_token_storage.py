"""Cloudflare credential API security tests."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import BackgroundTasks, HTTPException
from starlette.requests import Request

from core.config import Settings
from data_platform.api.auth import AuthUser
from data_platform.api.routers import cloudflare_account, email_scan, integrations
from data_platform.api.routers.cloudflare_account import (
    CloudflareTokenSaveRequest,
    get_workspace_cloudflare_token,
    save_workspace_cloudflare_token,
)
from data_platform.api.routers.email_scan import (
    EmailScanRequest,
    scan_email,
    upload_quarantine_content,
)
from data_platform.api.routers.integrations import (
    CloudflareSetupRequest,
    TeardownRequest,
    cloudflare_status,
    setup_cloudflare,
    teardown_cloudflare,
)
from data_platform.services.notification_policy import notification_is_allowed


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


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/integrations/cloudflare/setup",
            "headers": [],
            "client": ("127.0.0.1", 4000),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


def test_phishing_email_notification_respects_opt_out() -> None:
    """A disabled phishing preference suppresses the outbound notification."""
    assert not notification_is_allowed(
        {"notify_phishing": 0, "quiet_hours_enabled": 0},
        datetime(2026, 7, 15, 12, tzinfo=timezone.utc),
    )


def test_notification_master_switch_and_event_switches_are_independent() -> None:
    """Each domain has one master switch and explicit event-type switches."""
    now = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)
    assert not notification_is_allowed(
        {"email_enabled": 0, "notify_phishing": 1, "notify_domain_shield": 1},
        now,
        "phishing",
    )
    assert not notification_is_allowed(
        {"email_enabled": 1, "notify_phishing": 1, "notify_domain_shield": 0},
        now,
        "domain_shield",
    )
    assert notification_is_allowed(
        {"email_enabled": 1, "notify_phishing": 1, "notify_domain_shield": 0},
        now,
        "phishing",
    )


def test_quiet_hours_use_recipient_timezone_across_midnight() -> None:
    """Overnight quiet hours suppress only the configured local interval."""
    preference = {
        "notify_phishing": 1,
        "quiet_hours_enabled": 1,
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "07:00",
        "timezone": "Europe/Paris",
    }
    assert not notification_is_allowed(
        preference, datetime(2026, 7, 15, 21, 30, tzinfo=timezone.utc)
    )
    assert notification_is_allowed(preference, datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_token_get_is_write_only(monkeypatch) -> None:
    """The browser receives configuration state, never the provider secret."""

    async def query(sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if "cloudflare_integration" in sql:
            return [{"api_token": "enc:v1:ciphertext"}]
        return [{"api_token": "enc:v1:ciphertext"}]

    monkeypatch.setattr(cloudflare_account, "ensure_runtime_tables", lambda: None)
    monkeypatch.setattr(cloudflare_account, "_async_query", query)

    response = await get_workspace_cloudflare_token(_user())
    assert response == {"configured": True}
    assert "api_token" not in response


@pytest.mark.asyncio
async def test_cloudflare_status_reads_latest_workspace_integration(monkeypatch) -> None:
    """Status lookup is workspace-scoped and does not require a request body."""
    calls: list[tuple[Any, ...]] = []

    async def query(_sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        calls.append(params)
        return [
            {
                "id": "integration-1",
                "user_email": "owner@example.test",
                "zone_name": "example.test",
                "destination_email": "owner@example.test",
                "worker_name": "sicurre-example",
                "status": "active",
                "api_token": "encrypted",
                "error_message": None,
                "created_at": "now",
                "updated_at": "now",
            }
        ]

    monkeypatch.setattr(integrations, "_ensure_tables", lambda: None)
    monkeypatch.setattr(integrations, "_async_query", query)

    response = await cloudflare_status(_user())

    assert response["status"] == "active"
    assert calls == [("workspace-1",)]


@pytest.mark.asyncio
async def test_token_save_persists_ciphertext(monkeypatch) -> None:
    """A verified provider token is encrypted before any database write."""
    writes: list[tuple[str, tuple[Any, ...]]] = []

    class Provisioner:
        def __init__(self, api_token: str) -> None:
            assert api_token == "cloudflare-secret"

        async def verify_token(self) -> bool:
            return True

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        writes.append((sql, params))
        return []

    monkeypatch.setattr(cloudflare_account, "CloudflareProvisioner", Provisioner)
    monkeypatch.setattr(cloudflare_account, "_async_query", query)

    response = await save_workspace_cloudflare_token(
        CloudflareTokenSaveRequest(cf_api_token="cloudflare-secret"),
        _user(),
    )

    assert response == {"status": "saved"}
    persisted = str(writes[-1][1][1])
    assert persisted.startswith("enc:v1:")
    assert "cloudflare-secret" not in persisted


@pytest.mark.asyncio
async def test_quarantine_mime_upload_is_workspace_scoped_and_idempotent(monkeypatch) -> None:
    """The Worker can store raw MIME once without exposing a browser upload route."""
    writes: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        writes.append((sql, params))
        if "FROM cloudflare_integration" in sql:
            return [{"workspace_id": "workspace-1", "zone_name": "example.test"}]
        if "FROM app_quarantine_item" in sql:
            return [{"raw_storage_uri": None, "raw_content_hash": None}]
        return []

    class Store:
        async def write(self, **kwargs: Any) -> SimpleNamespace:
            assert kwargs["workspace_id"] == "workspace-1"
            assert kwargs["payload"] == b"From: sender@example.test\r\n\r\nBody"
            return SimpleNamespace(
                storage_uri="file:///quarantine/item.eml",
                content_hash="hash",
                size_bytes=len(kwargs["payload"]),
            )

    body = b"From: sender@example.test\r\n\r\nBody"
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "PUT",
            "path": "/",
            "headers": [],
            "client": ("127.0.0.1", 4000),
        },
        receive,
    )
    monkeypatch.setattr(email_scan, "_async_query", query)
    monkeypatch.setattr(email_scan, "build_quarantine_store", lambda _settings: Store())

    response = await upload_quarantine_content(
        "item-1",
        request,
        x_sicurre_secret="worker-secret",
    )

    assert response == {"status": "stored", "idempotent": False}
    assert any("workspace_id = ?" in sql for sql, _ in writes)
    assert any("example.test" in params for _, params in writes)


@pytest.mark.asyncio
async def test_phishing_scan_persists_only_a_redacted_quarantine_preview(monkeypatch) -> None:
    """Exact message content belongs in private MIME custody, not the app database."""
    writes: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        writes.append((sql, params))
        if "FROM cloudflare_integration" in sql:
            return [
                {
                    "id": "integration-1",
                    "user_email": "owner@example.test",
                    "workspace_id": "workspace-1",
                    "workspace_member_user_id": "user-1",
                    "zone_name": "example.test",
                    "status": "active",
                }
            ]
        if 'SELECT name FROM "user"' in sql:
            return [{"name": "Owner"}]
        if "FROM app_security_rule" in sql:
            return [{"rule_type": "blocklist", "pattern": "example.test"}]
        return []

    async def noop_notification(**_: Any) -> None:
        return None

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/email/scan",
            "headers": [],
            "client": ("127.0.0.1", 4000),
        }
    )
    monkeypatch.setattr(email_scan, "ensure_runtime_tables", lambda: None)
    monkeypatch.setattr(email_scan, "_async_query", query)
    monkeypatch.setattr(email_scan, "send_loops_transactional", noop_notification)
    clock = iter((10.0, 10.125))
    monkeypatch.setattr(email_scan, "perf_counter", lambda: next(clock))

    response = await scan_email(
        request,
        EmailScanRequest(
            message_id="message-1",
            sender="attacker@example.test",
            subject="Urgent transfer",
            text="Write to victim@example.test using IBAN FR76 3000 6000 0112 3456 7890 189.",
        ),
        x_sicurre_secret="worker-secret",
    )

    assert response.verdict == "quarantine"
    assert response.latency_ms == 125.0
    quarantine_insert = next(
        params for sql, params in writes if "INSERT INTO app_quarantine_item" in sql
    )
    assert quarantine_insert[6] == "Write to [EMAIL] using IBAN [IBAN]."
    inference_insert = next(
        params for sql, params in writes if "INSERT INTO app_inference_event" in sql
    )
    assert inference_insert[17] == 125.0


@pytest.mark.asyncio
async def test_scan_reports_inference_outage_instead_of_marking_email_safe(monkeypatch) -> None:
    """An unavailable classifier must never produce a successful safe verdict."""

    async def query(sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if "FROM cloudflare_integration" in sql:
            return [
                {
                    "id": "integration-1",
                    "user_email": "owner@example.test",
                    "workspace_id": "workspace-1",
                    "workspace_member_user_id": "user-1",
                    "zone_name": "example.test",
                    "status": "active",
                }
            ]
        return []

    class UnavailableClient:
        def __init__(self, **_: Any) -> None:
            pass

        async def __aenter__(self) -> UnavailableClient:
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def post(self, *_: Any, **__: Any) -> httpx.Response:
            raise httpx.ConnectError("classifier unavailable")

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/email/scan",
            "headers": [],
            "client": ("127.0.0.1", 4000),
        }
    )
    monkeypatch.setattr(email_scan, "ensure_runtime_tables", lambda: None)
    monkeypatch.setattr(email_scan, "_async_query", query)
    monkeypatch.setattr(email_scan.httpx, "AsyncClient", UnavailableClient)

    with pytest.raises(HTTPException) as exc_info:
        await scan_email(
            request,
            EmailScanRequest(
                message_id="message-1",
                sender="sender@example.test",
                subject="Invoice",
                text="Please review",
            ),
            x_sicurre_secret="worker-secret",
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Inference service is temporarily unavailable"


@pytest.mark.asyncio
async def test_teardown_uses_requested_integration_and_stored_token(monkeypatch) -> None:
    """Domain removal targets the selected tenant resource without asking for the token again."""
    statements: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        statements.append((sql, params))
        if "WHERE id = ? AND workspace_id = ?" in sql:
            return [
                {
                    "id": "integration-2",
                    "status": "active",
                    "api_token": "enc:v1:value",
                    "zone_id": "zone-2",
                    "account_id": "account-2",
                    "worker_name": "worker-2",
                    "rule_id": "rule-2",
                    "zone_name": "two.example",
                }
            ]
        return []

    deployed: list[dict[str, Any]] = []

    class Provisioner:
        def __init__(self, api_token: str) -> None:
            assert api_token == "stored-secret"

        async def teardown(self, **kwargs: Any) -> None:
            assert kwargs["zone_id"] == "zone-2"

        async def get_dns_records(self, zone_id: str) -> list[dict[str, str]]:
            assert zone_id == "zone-2"
            return [
                {
                    "type": "TXT",
                    "name": "_dmarc.two.example",
                    "content": "v=DMARC1; p=reject; "
                    "rua=mailto:owner@two.example,mailto:dmarc@sicurre.com",
                }
            ]

        async def deploy_dns_record(self, **kwargs: Any) -> None:
            deployed.append(kwargs)

    monkeypatch.setattr(integrations, "_ensure_tables", lambda: None)
    monkeypatch.setattr(integrations, "_async_query", query)
    monkeypatch.setattr(integrations, "decrypt_secret", lambda *_args, **_kwargs: "stored-secret")
    monkeypatch.setattr(integrations, "CloudflareProvisioner", Provisioner)

    response = await teardown_cloudflare(TeardownRequest(integration_id="integration-2"), _user())

    assert response == {
        "status": "removed",
        "zone_name": "two.example",
        "dmarc_reporting_withdrawn": True,
    }
    assert statements[0][1] == ("integration-2", "workspace-1")
    assert any("DELETE FROM cloudflare_integration" in sql for sql, _ in statements)

    # The domain stops reporting to Sicurre, and keeps its own reporting.
    assert len(deployed) == 1, "the DMARC record was not rewritten on teardown"
    assert deployed[0]["name"] == "_dmarc.two.example"
    assert deployed[0]["match_prefix"] == "v=DMARC1"
    assert deployed[0]["content"] == "v=DMARC1; p=reject; rua=mailto:owner@two.example"


@pytest.mark.asyncio
async def test_teardown_preserves_local_state_when_cloudflare_fails(monkeypatch) -> None:
    """Provider failure remains visible and does not orphan live routing resources."""
    statements: list[str] = []

    async def query(sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        statements.append(sql)
        if sql.startswith("SELECT * FROM cloudflare_integration"):
            return [
                {
                    "id": "integration-1",
                    "status": "active",
                    "api_token": "token",
                    "zone_id": "zone-1",
                    "account_id": "account-1",
                    "worker_name": "worker-1",
                    "rule_id": "rule-1",
                    "zone_name": "one.example",
                }
            ]
        return []

    class Provisioner:
        def __init__(self, api_token: str) -> None:
            pass

        async def teardown(self, **_kwargs: Any) -> None:
            raise integrations.CloudflareAPIError("Email Routing: Edit permission is missing")

    monkeypatch.setattr(integrations, "_ensure_tables", lambda: None)
    monkeypatch.setattr(integrations, "_async_query", query)
    monkeypatch.setattr(integrations, "decrypt_secret", lambda *_args, **_kwargs: "stored-secret")
    monkeypatch.setattr(integrations, "CloudflareProvisioner", Provisioner)

    with pytest.raises(HTTPException) as exc_info:
        await teardown_cloudflare(TeardownRequest(integration_id="integration-1"), _user())

    assert exc_info.value.status_code == 502
    assert "Email Routing: Edit permission is missing" in exc_info.value.detail
    assert not any(sql.startswith("DELETE FROM cloudflare_integration") for sql in statements)


@pytest.mark.asyncio
async def test_teardown_discards_failed_local_attempt_without_provider_token(monkeypatch) -> None:
    """A failed attempt with no remote resources can always be removed locally."""
    statements: list[str] = []

    async def query(sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        statements.append(sql)
        if sql.startswith("SELECT * FROM cloudflare_integration"):
            return [
                {
                    "id": "integration-failed",
                    "status": "error",
                    "api_token": None,
                    "zone_id": "",
                    "account_id": "",
                    "worker_name": "",
                    "rule_id": "unknown",
                    "zone_name": "failed.example",
                }
            ]
        return []

    class UnexpectedProvisioner:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Local cleanup must not call Cloudflare")

    monkeypatch.setattr(integrations, "_ensure_tables", lambda: None)
    monkeypatch.setattr(integrations, "_async_query", query)
    monkeypatch.setattr(integrations, "CloudflareProvisioner", UnexpectedProvisioner)

    response = await teardown_cloudflare(
        TeardownRequest(integration_id="integration-failed"), _user()
    )

    assert response == {
        "status": "removed",
        "zone_name": "failed.example",
        "dmarc_reporting_withdrawn": True,
    }
    assert any(sql.startswith("DELETE FROM cloudflare_integration") for sql in statements)
    assert not any(sql.startswith("DELETE FROM app_cloudflare_config") for sql in statements)


@pytest.mark.asyncio
async def test_setup_replaces_failed_local_attempt_using_saved_token(monkeypatch) -> None:
    """Retry discards stale local state and starts a fresh provision operation."""
    statements: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        statements.append((sql, params))
        if "FROM cloudflare_integration" in sql:
            return [
                {
                    "id": "integration-failed",
                    "status": "error",
                    "zone_id": "",
                    "account_id": "",
                    "worker_name": "",
                }
            ]
        if "SELECT api_token FROM app_cloudflare_config" in sql:
            return [{"api_token": "encrypted-token"}]
        return []

    async def sync_dns(**_kwargs: Any) -> dict[str, Any]:
        return {"status": "unchanged"}

    monkeypatch.setattr(integrations, "_ensure_tables", lambda: None)
    monkeypatch.setattr(integrations, "_async_query", query)
    monkeypatch.setattr(integrations, "decrypt_secret", lambda *_args, **_kwargs: "saved-token")
    monkeypatch.setattr(integrations, "sync_domain_shield_dns", sync_dns)

    response = await setup_cloudflare(
        CloudflareSetupRequest(
            zone_name="failed.example",
            destination_email="owner@example.test",
        ),
        BackgroundTasks(),
        _request(),
        _user(),
    )

    assert response["status"] == "provisioning"
    assert any(
        sql.startswith("DELETE FROM cloudflare_integration")
        and params == ("integration-failed", "workspace-1")
        for sql, params in statements
    )
    assert any("INSERT INTO cloudflare_integration" in sql for sql, _ in statements)


@pytest.mark.asyncio
async def test_teardown_uses_workspace_token_when_integration_token_is_absent(monkeypatch) -> None:
    """Live teardown falls back to the workspace credential without browser input."""

    async def query(sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if sql.startswith("SELECT * FROM cloudflare_integration"):
            return [
                {
                    "id": "integration-1",
                    "status": "active",
                    "api_token": None,
                    "zone_id": "zone-1",
                    "account_id": "account-1",
                    "worker_name": "worker-1",
                    "rule_id": "rule-1",
                    "zone_name": "one.example",
                }
            ]
        if "SELECT api_token FROM app_cloudflare_config" in sql:
            return [{"api_token": "workspace-token"}]
        return []

    class Provisioner:
        def __init__(self, api_token: str) -> None:
            assert api_token == "decrypted-token"

        async def teardown(self, **_kwargs: Any) -> None:
            return None

    monkeypatch.setattr(integrations, "_ensure_tables", lambda: None)
    monkeypatch.setattr(integrations, "_async_query", query)
    monkeypatch.setattr(integrations, "decrypt_secret", lambda *_args, **_kwargs: "decrypted-token")
    monkeypatch.setattr(integrations, "CloudflareProvisioner", Provisioner)

    response = await teardown_cloudflare(TeardownRequest(integration_id="integration-1"), _user())

    assert response["status"] == "removed"


@pytest.mark.asyncio
async def test_live_teardown_reports_missing_provider_token(monkeypatch) -> None:
    """A live resource is never silently detached when no provider token exists."""

    async def query(sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if sql.startswith("SELECT * FROM cloudflare_integration"):
            return [
                {
                    "id": "integration-1",
                    "status": "active",
                    "api_token": None,
                    "zone_id": "zone-1",
                    "account_id": "account-1",
                    "worker_name": "worker-1",
                    "rule_id": "rule-1",
                    "zone_name": "one.example",
                }
            ]
        return []

    monkeypatch.setattr(integrations, "_ensure_tables", lambda: None)
    monkeypatch.setattr(integrations, "_async_query", query)

    with pytest.raises(HTTPException) as exc_info:
        await teardown_cloudflare(TeardownRequest(integration_id="integration-1"), _user())

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Cloudflare API token is not configured"


@pytest.mark.asyncio
async def test_teardown_of_the_platform_zone_keeps_sicurre_dmarc_reporting(monkeypatch) -> None:
    """sicurre.com hosts the DMARC mailbox itself: withdrawing it would stop the platform's reports."""
    statements: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        statements.append((sql, params))
        if "WHERE id = ? AND workspace_id = ?" in sql:
            return [
                {
                    "id": "integration-platform",
                    "status": "active",
                    "api_token": "enc:v1:value",
                    "zone_id": "zone-platform",
                    "account_id": "account-platform",
                    "worker_name": "sicurre-gw-client",
                    "rule_id": "rule-client",
                    "zone_name": "Sicurre.com.",
                }
            ]
        return []

    torn_down: list[dict[str, Any]] = []
    deployed: list[dict[str, Any]] = []

    class Provisioner:
        def __init__(self, api_token: str) -> None:
            assert api_token == "stored-secret"

        async def teardown(self, **kwargs: Any) -> None:
            torn_down.append(kwargs)

        async def get_dns_records(self, zone_id: str) -> list[dict[str, str]]:
            return [
                {
                    "type": "TXT",
                    "name": "_dmarc.sicurre.com",
                    "content": "v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com",
                }
            ]

        async def deploy_dns_record(self, **kwargs: Any) -> None:
            deployed.append(kwargs)

    monkeypatch.setattr(integrations, "_ensure_tables", lambda: None)
    monkeypatch.setattr(integrations, "_async_query", query)
    monkeypatch.setattr(integrations, "decrypt_secret", lambda *_args, **_kwargs: "stored-secret")
    monkeypatch.setattr(integrations, "CloudflareProvisioner", Provisioner)

    response = await teardown_cloudflare(
        TeardownRequest(integration_id="integration-platform"), _user()
    )

    assert response == {
        "status": "removed",
        "zone_name": "Sicurre.com.",
        "dmarc_reporting_withdrawn": True,
    }
    # The client connection's own rule and Worker still go through the provisioner,
    # which keeps whatever Worker the catch-all uses.
    assert torn_down == [
        {
            "zone_id": "zone-platform",
            "account_id": "account-platform",
            "worker_name": "sicurre-gw-client",
            "rule_id": "rule-client",
            "keep_worker": False,
        }
    ]
    assert deployed == [], "Sicurre's own DMARC record was rewritten"
    assert any("DELETE FROM cloudflare_integration" in sql for sql, _ in statements)


def _teardown_fixture(monkeypatch, worker_name: str, shared_rows: list[dict[str, Any]]):
    """Wire the disconnect route for one integration; return the recorded teardown calls."""

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if "WHERE id = ? AND workspace_id = ?" in sql:
            return [
                {
                    "id": "integration-1",
                    "status": "active",
                    "api_token": "enc:v1:value",
                    "zone_id": "zone-1",
                    "account_id": "account-1",
                    "worker_name": worker_name,
                    "rule_id": "rule-1",
                    "zone_name": "one.example",
                }
            ]
        if "WHERE worker_name = ? AND id <> ?" in sql:
            assert params == (worker_name, "integration-1")
            return shared_rows
        return []

    calls: list[dict[str, Any]] = []

    class Provisioner:
        def __init__(self, api_token: str) -> None:
            pass

        async def teardown(self, **kwargs: Any) -> None:
            calls.append(kwargs)

        async def get_dns_records(self, zone_id: str) -> list[dict[str, str]]:
            return []

        async def deploy_dns_record(self, **kwargs: Any) -> None:
            raise AssertionError("no DMARC rewrite expected")

    monkeypatch.setattr(integrations, "_ensure_tables", lambda: None)
    monkeypatch.setattr(integrations, "_async_query", query)
    monkeypatch.setattr(integrations, "decrypt_secret", lambda *_args, **_kwargs: "stored-secret")
    monkeypatch.setattr(integrations, "CloudflareProvisioner", Provisioner)
    return calls


@pytest.mark.asyncio
async def test_teardown_keeps_a_worker_another_integration_uses(monkeypatch) -> None:
    """vinse.app's July and July-22 integrations share one Worker named after the zone."""
    calls = _teardown_fixture(monkeypatch, "sicurre-gw-shared", [{"id": "integration-2"}])

    await teardown_cloudflare(TeardownRequest(integration_id="integration-1"), _user())

    assert calls[0]["keep_worker"] is True


@pytest.mark.asyncio
async def test_teardown_keeps_a_protected_platform_worker(monkeypatch) -> None:
    """The platform catch-all routes to this Worker from another zone."""
    monkeypatch.setattr(
        integrations,
        "get_settings",
        lambda: Settings(_env_file=None, protected_worker_names=" sicurre-gw-platform , other "),
    )
    calls = _teardown_fixture(monkeypatch, "sicurre-gw-platform", [])

    await teardown_cloudflare(TeardownRequest(integration_id="integration-1"), _user())

    assert calls[0]["keep_worker"] is True


@pytest.mark.asyncio
async def test_teardown_deletes_a_worker_nothing_else_uses(monkeypatch) -> None:
    monkeypatch.setattr(
        integrations, "get_settings", lambda: Settings(_env_file=None, protected_worker_names="")
    )
    calls = _teardown_fixture(monkeypatch, "sicurre-gw-alone", [])

    await teardown_cloudflare(TeardownRequest(integration_id="integration-1"), _user())

    assert calls[0]["keep_worker"] is False


def test_the_platform_worker_is_protected_by_default() -> None:
    assert "sicurre-gw-9e622bde" in Settings(_env_file=None).protected_worker_name_set


def _teardown_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "integration-3",
        "status": "active",
        "api_token": "enc:v1:value",
        "zone_id": "zone-3",
        "account_id": "account-3",
        "worker_name": "worker-3",
        "rule_id": "rule-3",
        "zone_name": "three.example",
        "user_email": "owner@three.example",
        "destination_email": "owner.inbox@gmail.test",
    }
    row.update(overrides)
    return row


def _teardown_wiring(monkeypatch, row: dict[str, Any], restore_error: Exception | None = None) -> list[tuple[Any, ...]]:
    restored: list[tuple[Any, ...]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if "WHERE id = ? AND workspace_id = ?" in sql:
            return [row]
        return []

    class Provisioner:
        def __init__(self, api_token: str) -> None:
            pass

        async def teardown(self, **_kwargs: Any) -> None:
            return None

        async def restore_forwarding(self, zone_id: str, address: str, forward_to: str) -> bool:
            if restore_error is not None:
                raise restore_error
            restored.append((zone_id, address, forward_to))
            return True

        async def get_dns_records(self, _zone_id: str) -> list[dict[str, str]]:
            return []

        async def deploy_dns_record(self, **_kwargs: Any) -> None:
            return None

    monkeypatch.setattr(integrations, "_ensure_tables", lambda: None)
    monkeypatch.setattr(integrations, "_async_query", query)
    monkeypatch.setattr(integrations, "decrypt_secret", lambda *_args, **_kwargs: "stored-secret")
    monkeypatch.setattr(integrations, "CloudflareProvisioner", Provisioner)
    return restored


@pytest.mark.asyncio
async def test_teardown_gives_the_protected_address_its_forward_back(monkeypatch) -> None:
    """Without it, mail to the address has no route once the Worker rule is gone."""
    restored = _teardown_wiring(monkeypatch, _teardown_row())

    response = await teardown_cloudflare(TeardownRequest(integration_id="integration-3"), _user())

    assert response["status"] == "removed"
    assert restored == [("zone-3", "owner@three.example", "owner.inbox@gmail.test")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"user_email": "owner@elsewhere.example"},
        {"destination_email": "owner@three.example"},
        {"destination_email": ""},
        {"user_email": ""},
    ],
)
async def test_teardown_restores_nothing_it_cannot_route(monkeypatch, overrides: dict[str, Any]) -> None:
    """An address off the zone, or a forward to itself, is not a rule to create."""
    restored = _teardown_wiring(monkeypatch, _teardown_row(**overrides))

    await teardown_cloudflare(TeardownRequest(integration_id="integration-3"), _user())

    assert restored == []


@pytest.mark.asyncio
async def test_teardown_restores_a_subdomain_address(monkeypatch) -> None:
    restored = _teardown_wiring(monkeypatch, _teardown_row(user_email="owner@mail.three.example"))

    await teardown_cloudflare(TeardownRequest(integration_id="integration-3"), _user())

    assert restored == [("zone-3", "owner@mail.three.example", "owner.inbox@gmail.test")]


@pytest.mark.asyncio
async def test_a_failed_forward_restore_does_not_fail_the_teardown(monkeypatch) -> None:
    """The Worker and rule are already gone: the disconnect still completes."""
    _teardown_wiring(
        monkeypatch,
        _teardown_row(),
        restore_error=integrations.CloudflareAPIError("destination address not verified"),
    )

    response = await teardown_cloudflare(TeardownRequest(integration_id="integration-3"), _user())

    assert response["status"] == "removed"
