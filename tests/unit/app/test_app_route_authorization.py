"""Authorization tests for application-only operational routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from data_platform.api.auth import AuthUser
from data_platform.api.routers import app_routes
from data_platform.api.routers.app_routes import (
    AlertPreferenceUpdate,
    SecurityRuleCreate,
    SupportRequestCreate,
    create_support_request,
    delete_quarantine_item,
    dismiss_alert,
    get_dmarc_report_summary,
    import_dmarc_report,
    list_datasets_alias,
    release_quarantine_item,
    run_pipeline,
)

DMARC_XML = b"""<feedback>
<report_metadata><org_name>Google</org_name><report_id>report-1</report_id>
<date_range><begin>1700000000</begin><end>1700086400</end></date_range></report_metadata>
<policy_published><domain>example.test</domain></policy_published>
<record><row><source_ip>192.0.2.1</source_ip><count>2</count>
<policy_evaluated><disposition>none</disposition></policy_evaluated></row>
<identifiers><header_from>example.test</header_from></identifiers>
<auth_results><dkim><result>pass</result></dkim><spf><result>pass</result></spf></auth_results>
</record></feedback>"""


def _user(*, platform_admin: bool) -> AuthUser:
    return AuthUser(
        id="user-1",
        email="owner@example.test",
        display_name="Owner",
        role="admin" if platform_admin else "owner",
        workspace_id="workspace-1",
        workspace_name="Workspace",
        is_platform_admin=platform_admin,
    )


@pytest.mark.asyncio
async def test_customer_cannot_read_global_datasets() -> None:
    """Global training lineage remains restricted to platform operators."""
    with pytest.raises(HTTPException) as exc_info:
        await list_datasets_alias(session=None, current_user=_user(platform_admin=False))  # type: ignore[arg-type]

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_customer_cannot_trigger_host_pipeline() -> None:
    """A customer session cannot enqueue a host-side scheduler command."""
    tasks = BackgroundTasks()

    with pytest.raises(HTTPException) as exc_info:
        await run_pipeline(tasks, _user(platform_admin=False))

    assert exc_info.value.status_code == 403
    assert tasks.tasks == []


@pytest.mark.asyncio
async def test_dmarc_summary_rejects_unconnected_domain(monkeypatch) -> None:
    """A workspace cannot claim or inspect a domain it has not connected."""

    async def query(_sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    with pytest.raises(HTTPException) as exc_info:
        await get_dmarc_report_summary("other.example", _user(platform_admin=False))

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_dmarc_import_is_idempotent(monkeypatch) -> None:
    """Provider retries do not duplicate aggregate-report records."""
    inserted = False

    async def query(sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        nonlocal inserted
        if sql.startswith("SELECT 1 FROM cloudflare_integration"):
            return [{"1": 1}]
        if "INSERT INTO app_dmarc_report_summary" in sql:
            if inserted:
                return []
            inserted = True
            return [{"id": "row-1"}]
        return []

    def request() -> Request:
        sent = False

        async def receive() -> dict[str, Any]:
            nonlocal sent
            if sent:
                return {"type": "http.request", "body": b"", "more_body": False}
            sent = True
            return {"type": "http.request", "body": DMARC_XML, "more_body": False}

        return Request({"type": "http", "method": "POST", "path": "/"}, receive)

    monkeypatch.setattr(app_routes, "_ensure_app_runtime_tables", lambda: None)
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    first = await import_dmarc_report("example.test", request(), _user(platform_admin=False))
    replay = await import_dmarc_report("example.test", request(), _user(platform_admin=False))

    assert first == {"status": "imported", "record_count": 1}
    assert replay == {"status": "already_imported", "record_count": 0}


@pytest.mark.asyncio
async def test_domain_shield_cache_ages_ssl_days(monkeypatch) -> None:
    """Cached certificate validity reflects elapsed days without a fresh scan."""

    async def allow_domain(_domain: str, _workspace_id: str) -> None:
        return None

    async def blocklists(_domain: str, **_kwargs: object) -> tuple[list[str], list[str]]:
        return [], []

    updated_at = (datetime.now(UTC) - timedelta(days=3)).isoformat()

    async def query(_sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return [{
            "reputation_score": 100,
            "ssl_days_remaining": 10,
            "updated_at": updated_at,
            "spf_valid": 1,
            "spf_record": "v=spf1 ~all",
            "dkim_valid": 1,
            "dkim_record": "v=DKIM1",
            "dmarc_valid": 1,
            "dmarc_record": "v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com",
            "dmarc_policy": "reject",
            "ssl_valid": 1,
        }]

    monkeypatch.setattr(app_routes, "_require_workspace_domain", allow_domain)
    monkeypatch.setattr(app_routes, "_check_domain_blacklists", blocklists)
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    result = await app_routes.check_domain_shield_status(
        "example.test", refresh=False, current_user=_user(platform_admin=False)
    )

    assert result["ssl"]["days_remaining"] == 7
    assert result["ssl"]["valid"] is True


@pytest.mark.asyncio
async def test_domain_shield_marks_uninspectable_certificate_unavailable(monkeypatch) -> None:
    """A failed public TLS inspection is never replaced by a fabricated lifetime."""

    async def allow_domain(_domain: str, _workspace_id: str) -> None:
        return None

    async def blocklists(_domain: str, **_kwargs: object) -> tuple[list[str], list[str]]:
        return [], []

    async def query(_sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return []

    async def to_thread(function: Any, *_args: Any) -> Any:
        if function is app_routes._get_ssl_expiry_days:
            return -1
        raise RuntimeError("DNS unavailable")

    monkeypatch.setattr(app_routes, "_require_workspace_domain", allow_domain)
    monkeypatch.setattr(app_routes, "_check_domain_blacklists", blocklists)
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)
    monkeypatch.setattr(app_routes.asyncio, "to_thread", to_thread)

    result = await app_routes.check_domain_shield_status(
        "example.test", refresh=True, current_user=_user(platform_admin=False)
    )

    assert result["ssl"] == {
        "valid": False,
        "days_remaining": 0,
        "auto_renew": False,
        "error": "Unable to inspect the public certificate",
    }


@pytest.mark.asyncio
async def test_admin_can_enqueue_allowlisted_pipeline() -> None:
    """A platform admin can enqueue only the fixed pipeline callable."""
    tasks = BackgroundTasks()

    response = await run_pipeline(tasks, _user(platform_admin=True))

    assert response == {"run_id": "incremental-pipeline-run-triggered"}
    assert len(tasks.tasks) == 1
    task: Any = tasks.tasks[0]
    assert task.func.__name__ == "execute_pipeline"


@pytest.mark.asyncio
async def test_quarantine_release_rejects_missing_original_content(monkeypatch) -> None:
    """Legacy preview-only records cannot be falsely presented as delivered."""
    queries: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        queries.append((sql, params))
        return [{"id": "held-1", "status": "held", "raw_storage_uri": None}]

    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    with pytest.raises(HTTPException) as exc_info:
        await release_quarantine_item("held-1", _user(platform_admin=False))

    assert exc_info.value.status_code == 409
    assert len(queries) == 1
    assert "workspace_id = ?" in queries[0][0]
    assert "UPDATE" not in queries[0][0]


@pytest.mark.asyncio
async def test_quarantine_release_delivers_original_mime_once(monkeypatch) -> None:
    """A held item is claimed, delivered, recorded, and removed from raw custody."""
    queries: list[tuple[str, tuple[Any, ...]]] = []
    deleted: list[str] = []
    item = {
        "id": "held-1",
        "status": "held",
        "raw_storage_uri": "file:///quarantine/held-1.eml",
        "message_id": "event-1",
        "safety_verdict": "phishing",
    }

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        queries.append((sql, params))
        if sql.startswith("SELECT * FROM app_quarantine_item"):
            return [item]
        if sql.startswith("SELECT account_id"):
            return [
                {
                    "account_id": "account-1",
                    "zone_id": "zone-1",
                    "zone_name": "example.test",
                    "destination_email": "owner@example.test",
                    "api_token": "token",
                }
            ]
        if "RETURNING id" in sql:
            return [{"id": "held-1"}]
        return []

    class Store:
        async def read(self, uri: str) -> bytes:
            assert uri == item["raw_storage_uri"]
            return b"From: sender@example.net\r\n\r\nOriginal"

        async def delete(self, uri: str) -> None:
            deleted.append(uri)

    async def deliver(**kwargs: Any) -> SimpleNamespace:
        assert kwargs["raw_mime"].endswith(b"Original")
        return SimpleNamespace(
            message_id="delivery-1",
            recipient="owner@example.test",
            queued=False,
        )

    async def sending_address(**_kwargs: Any) -> str:
        return "quarantine@example.test"

    monkeypatch.setattr(app_routes, "async_query_auth_db", query)
    monkeypatch.setattr(app_routes, "build_quarantine_store", lambda _settings: Store())
    monkeypatch.setattr(app_routes, "send_raw_email", deliver)
    monkeypatch.setattr(app_routes, "resolve_sending_address", sending_address)

    response = await release_quarantine_item("held-1", _user(platform_admin=False))

    assert response["status"] == "released"
    assert response["delivery_message_id"] == "delivery-1"
    assert deleted == [item["raw_storage_uri"]]
    assert any("status = 'released'" in sql for sql, _ in queries)


@pytest.mark.asyncio
async def test_quarantine_delete_write_remains_workspace_scoped(monkeypatch) -> None:
    """Ownership remains in the mutation predicate, not only the preflight read."""
    queries: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        queries.append((sql, params))
        return [{"exists": 1}]

    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    assert await delete_quarantine_item("held-1", _user(platform_admin=False)) == {
        "status": "deleted"
    }
    update_sql, update_params = queries[-1]
    assert "WHERE id = ? AND workspace_id = ?" in update_sql
    assert "sender = '[deleted]'" in update_sql
    assert "body_text = ''" in update_sql
    assert update_params == ("held-1", "workspace-1")


@pytest.mark.asyncio
async def test_quarantine_delete_keeps_item_when_storage_fails(monkeypatch) -> None:
    """A custody failure cannot be presented as a successful deletion."""
    queries: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        queries.append((sql, params))
        return [{"raw_storage_uri": "r2://bucket/quarantine/workspace-1/held-1.eml"}]

    class Store:
        async def delete(self, _uri: str) -> None:
            raise RuntimeError("R2 unavailable")

    monkeypatch.setattr(app_routes, "async_query_auth_db", query)
    monkeypatch.setattr(app_routes, "build_quarantine_store", lambda _settings: Store())

    with pytest.raises(HTTPException) as exc_info:
        await delete_quarantine_item("held-1", _user(platform_admin=False))

    assert exc_info.value.status_code == 503
    assert len(queries) == 1


@pytest.mark.asyncio
async def test_alert_dismiss_write_remains_workspace_scoped(monkeypatch) -> None:
    """Alert dismissal cannot mutate another workspace after its ownership check."""
    queries: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        queries.append((sql, params))
        return [{"exists": 1}]

    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    assert await dismiss_alert("alert-1", _user(platform_admin=False)) == {"status": "dismissed"}
    update_sql, update_params = queries[-1]
    assert "WHERE id = ? AND workspace_id = ?" in update_sql
    assert update_params == ("alert-1", "workspace-1")


@pytest.mark.asyncio
async def test_support_request_is_tenant_scoped(monkeypatch) -> None:
    """Authenticated support requests persist the session workspace and member."""
    queries: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        queries.append((sql, params))
        return []

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/support/requests",
            "headers": [],
            "client": ("127.0.0.1", 4000),
        }
    )
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    response = await create_support_request(
        request,
        SupportRequestCreate(
            requester_name="Owner",
            requester_email="owner@example.com",
            category="dns",
            message="Cloudflare routing needs review.",
        ),
        _user(platform_admin=False),
    )

    assert response["status"] == "open"
    assert queries[0][1][1:3] == ("workspace-1", "user-1")


def test_alert_preferences_require_a_real_iana_timezone() -> None:
    """Quiet hours reject unknown zones instead of silently shifting to UTC."""
    with pytest.raises(ValidationError, match="valid IANA timezone"):
        AlertPreferenceUpdate(
            notify_phishing=True,
            notify_spam=False,
            quiet_hours_enabled=True,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            timezone="Mars/Olympus_Mons",
        )


def test_security_rules_are_normalized_for_case_insensitive_matching() -> None:
    """Saved sender and domain patterns use one canonical representation."""
    rule = SecurityRuleCreate(rule_type="blocklist", pattern="  Billing@Example.COM ")
    assert rule.pattern == "billing@example.com"
