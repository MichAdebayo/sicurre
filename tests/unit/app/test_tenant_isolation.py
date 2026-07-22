"""Tenant-isolation (IDOR) tests for every user-scoped application endpoint.

Each test authenticates as User A (workspace-1), then verifies that the
endpoint rejects or returns empty results when the resource belongs to
User B (workspace-2).  The data layer is monkeypatched so no real database
is needed — the assertion is that SQL predicates include workspace_id from
the authenticated session, never from request parameters.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from data_platform.api.auth import AuthUser
from data_platform.api.routers import app_routes, integrations
from data_platform.api.routers.app_routes import (
    FeedbackCreate,
    SecurityRuleCreate,
    StatusUpdate,
    create_feedback,
    create_security_rule,
    delete_quarantine_item,
    delete_security_rule,
    dismiss_alert,
    get_alert_preferences,
    get_kpis,
    get_threats,
    list_alert_history,
    list_cloudflare_integrations,
    list_quarantine,
    list_security_rules,
    release_and_whitelist_item,
    release_quarantine_item,
    update_alert_preferences,
    update_threat_status,
)
from data_platform.api.routers.integrations import (
    delete_workspace_cloudflare_token,
    get_workspace_cloudflare_token,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────

USER_A = AuthUser(
    id="user-a",
    email="alice@workspace-one.test",
    display_name="Alice",
    role="owner",
    workspace_id="workspace-1",
    workspace_name="Workspace One",
    is_platform_admin=False,
)

USER_B = AuthUser(
    id="user-b",
    email="bob@workspace-two.test",
    display_name="Bob",
    role="owner",
    workspace_id="workspace-2",
    workspace_name="Workspace Two",
    is_platform_admin=False,
)


def _tracking_query(
    rows_for_workspace: dict[str, list[dict[str, Any]]],
    *,
    default_table: str = "",
) -> tuple[list[tuple[str, tuple[Any, ...]]], Any]:
    """Return (captured_queries, async_query_fn) where the fn returns rows only
    when the workspace_id parameter matches the seeded data."""
    captured: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        captured.append((sql, params))
        # Identify which workspace_id was used in the query
        for ws_id, rows in rows_for_workspace.items():
            if ws_id in params:
                return rows
        return []

    return captured, query


def _foreign_resource_query(
    foreign_row: dict[str, Any],
) -> tuple[list[tuple[str, tuple[Any, ...]]], Any]:
    """Model an existing foreign row that leaks whenever workspace scoping is absent."""
    captured: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        captured.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "workspace_id" in normalized and USER_A.workspace_id in params:
            return []
        if normalized.startswith("select"):
            return [foreign_row]
        return []

    return captured, query


# ── Threats ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_threats_are_workspace_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /v1/threats for User A returns nothing when threats belong to workspace-2."""
    captured, query = _tracking_query(
        {
            "workspace-2": [
                {
                    "id": "threat-1",
                    "message_id": "threat-1",
                    "subject": "Phishing",
                    "sender": "bad@evil.test",
                    "body_preview": "Click here",
                    "verdict": "phishing",
                    "confidence": 0.99,
                    "received_at": "2026-07-15T12:00:00Z",
                    "status": "active",
                    "latency_ms": 42,
                    "explanation": None,
                }
            ],
        }
    )
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    result = await get_threats(USER_A)

    assert result == [], "User A must not see threats belonging to workspace-2"
    assert all("workspace-1" in params for _, params in captured)


@pytest.mark.asyncio
async def test_threat_status_update_cannot_cross_workspaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /v1/threats/{id}/status rejects when the threat belongs to workspace-2."""
    captured, query = _foreign_resource_query(
        {
            "id": "threat-owned-by-b",
            "message_id": "foreign-message",
            "subject": "Foreign threat",
            "sender": "foreign@example.test",
            "body_preview": "Foreign body",
            "verdict": "phishing",
            "confidence": 0.99,
            "received_at": "2026-07-15T00:00:00Z",
            "status": "active",
        }
    )
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    with pytest.raises(HTTPException) as exc_info:
        await update_threat_status("threat-owned-by-b", StatusUpdate(status="trashed"), USER_A)

    assert exc_info.value.status_code == 404
    # Verify workspace_id was in the WHERE clause
    assert any("workspace-1" in params for _, params in captured)


# ── Feedback ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_feedback_with_foreign_event_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /v1/feedback referencing a workspace-2 event is rejected."""
    captured, query = _foreign_resource_query({"id": "q-owned-by-b", "status": "held"})
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    with pytest.raises(HTTPException) as exc_info:
        await create_feedback(
            FeedbackCreate(
                event_id="event-in-workspace-2",
                feedback_type="false_positive",
                corrected_verdict="legitimate",
            ),
            USER_A,
        )

    assert exc_info.value.status_code == 404
    assert all("workspace_id" in sql.lower() for sql, _ in captured)
    assert all(USER_A.workspace_id in params for _, params in captured)
    assert any("workspace-1" in params for _, params in captured)


@pytest.mark.asyncio
async def test_feedback_without_event_scopes_to_calling_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /v1/feedback without event_id inserts into the caller's workspace."""
    captured, query = _foreign_resource_query({"raw_storage_uri": "file:///foreign/quarantine.eml"})

    async def insert_query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        captured.append((sql, params))
        return []

    monkeypatch.setattr(app_routes, "async_query_auth_db", insert_query)

    result = await create_feedback(
        FeedbackCreate(
            feedback_type="false_negative",
            corrected_verdict="phishing",
        ),
        USER_A,
    )

    assert result["feedback_type"] == "false_negative"
    insert_sql, insert_params = captured[0]
    assert "INSERT INTO app_feedback" in insert_sql
    assert insert_params[1] == "workspace-1", "Feedback must be scoped to the calling workspace"


# ── Quarantine ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quarantine_list_is_workspace_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /v1/quarantine returns empty for User A when items belong to workspace-2."""
    captured, query = _tracking_query(
        {
            "workspace-2": [
                {
                    "id": "q-1",
                    "message_id": "msg-1",
                    "sender": "bad@evil.test",
                    "subject": "Phish",
                    "body_text": "body",
                    "safety_verdict": "phishing",
                    "composite_score": 0.95,
                    "status": "held",
                    "created_at": "2026-07-15T00:00:00Z",
                    "expires_at": "2026-07-29T00:00:00Z",
                }
            ],
        }
    )
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    result = await list_quarantine(USER_A)

    assert result == [], "User A must not see quarantine items from workspace-2"


@pytest.mark.asyncio
async def test_quarantine_release_rejects_foreign_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /v1/quarantine/{id}/release rejects when item belongs to another workspace."""
    captured, query = _tracking_query({})
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    with pytest.raises(HTTPException) as exc_info:
        await release_quarantine_item("q-owned-by-b", USER_A)

    assert exc_info.value.status_code == 404
    assert all("workspace_id" in sql.lower() for sql, _ in captured)
    assert all(USER_A.workspace_id in params for _, params in captured)


@pytest.mark.asyncio
async def test_quarantine_delete_rejects_foreign_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DELETE /v1/quarantine/{id} rejects when item belongs to another workspace."""
    captured, query = _foreign_resource_query(
        {"id": "q-owned-by-b", "status": "held", "sender": "foreign@example.test"}
    )
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    with pytest.raises(HTTPException) as exc_info:
        await delete_quarantine_item("q-owned-by-b", USER_A)

    assert exc_info.value.status_code == 404
    assert all("workspace_id" in sql.lower() for sql, _ in captured)
    assert all(USER_A.workspace_id in params for _, params in captured)


@pytest.mark.asyncio
async def test_quarantine_whitelist_rejects_foreign_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /v1/quarantine/{id}/whitelist rejects when item belongs to another workspace."""
    captured, query = _foreign_resource_query({"id": "rule-owned-by-b"})
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    with pytest.raises(HTTPException) as exc_info:
        await release_and_whitelist_item("q-owned-by-b", USER_A)

    assert exc_info.value.status_code == 404
    assert all("workspace_id" in sql.lower() for sql, _ in captured)
    assert all(USER_A.workspace_id in params for _, params in captured)


# ── Alerts: Preferences ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_alert_preferences_read_is_workspace_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /v1/alerts/preferences reads only the caller's workspace."""
    captured: list[tuple[str, tuple[Any, ...]]] = []
    call_count = 0

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        nonlocal call_count
        captured.append((sql, params))
        call_count += 1
        if call_count == 1:
            return []  # no existing prefs → will insert default
        return [
            {
                "notify_phishing": 1,
                "notify_spam": 0,
                "quiet_hours_enabled": 0,
                "quiet_hours_start": "22:00",
                "quiet_hours_end": "07:00",
                "timezone": "Europe/Paris",
            }
        ]

    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    result = await get_alert_preferences(USER_A)

    assert result["timezone"] == "Europe/Paris"
    # All queries must reference workspace-1, never workspace-2
    assert all("workspace-1" in params for _, params in captured)


@pytest.mark.asyncio
async def test_alert_preferences_write_is_workspace_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PUT /v1/alerts/preferences writes only to the caller's workspace."""
    from data_platform.api.routers.app_routes import AlertPreferenceUpdate

    captured: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        captured.append((sql, params))
        return []

    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    result = await update_alert_preferences(
        AlertPreferenceUpdate(
            notify_phishing=True,
            notify_spam=False,
            quiet_hours_enabled=False,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            timezone="Europe/Paris",
        ),
        USER_A,
    )

    assert result == {"status": "updated"}
    sql, params = captured[0]
    assert params[0] == "workspace-1", "Preferences must be scoped to the calling workspace"


# ── Alerts: Rules ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_security_rules_list_is_workspace_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /v1/alerts/rules returns only the caller's workspace rules."""
    captured, query = _tracking_query(
        {
            "workspace-2": [
                {
                    "id": "rule-1",
                    "rule_type": "blocklist",
                    "pattern": "evil@test",
                    "created_at": "now",
                }
            ],
        }
    )
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    result = await list_security_rules(USER_A)

    assert result == [], "User A must not see rules from workspace-2"


@pytest.mark.asyncio
async def test_security_rule_create_is_workspace_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /v1/alerts/rules inserts into the caller's workspace."""
    captured: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        captured.append((sql, params))
        return []

    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    result = await create_security_rule(
        SecurityRuleCreate(rule_type="blocklist", pattern="phish@evil.test"),
        USER_A,
    )

    assert result["rule_type"] == "blocklist"
    sql, params = captured[0]
    assert params[1] == "workspace-1", "Rule must be scoped to the calling workspace"


@pytest.mark.asyncio
async def test_security_rule_delete_rejects_foreign_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DELETE /v1/alerts/rules/{id} rejects when rule belongs to another workspace."""
    captured, query = _foreign_resource_query({"id": "alert-owned-by-b"})
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    with pytest.raises(HTTPException) as exc_info:
        await delete_security_rule("rule-owned-by-b", USER_A)

    assert exc_info.value.status_code == 404
    assert all("workspace_id" in sql.lower() for sql, _ in captured)
    assert all(USER_A.workspace_id in params for _, params in captured)


# ── Alerts: History ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_alert_history_is_workspace_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /v1/alerts/history returns only the caller's workspace alerts."""
    captured, query = _tracking_query(
        {
            "workspace-2": [
                {"id": "alert-1", "title": "Threat", "message": "msg", "created_at": "now"}
            ],
        }
    )
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    result = await list_alert_history(USER_A)

    assert result == [], "User A must not see alerts from workspace-2"


@pytest.mark.asyncio
async def test_alert_dismiss_rejects_foreign_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /v1/alerts/history/{id}/dismiss rejects foreign alert."""
    captured, query = _tracking_query({})
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    with pytest.raises(HTTPException) as exc_info:
        await dismiss_alert("alert-owned-by-b", USER_A)

    assert exc_info.value.status_code == 404


# ── Cloudflare Integrations ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cloudflare_list_is_workspace_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /v1/integrations/cloudflare/list returns only the caller's integrations."""
    captured, query = _tracking_query(
        {
            "workspace-2": [
                {
                    "id": "int-1",
                    "user_email": "bob@test",
                    "zone_name": "bob.test",
                    "destination_email": "bob@inbox.test",
                    "worker_name": "sicurre-bob",
                    "status": "active",
                    "api_token": "encrypted",
                    "error_message": None,
                    "created_at": "now",
                    "updated_at": "now",
                }
            ],
        }
    )
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    result = await list_cloudflare_integrations(USER_A)

    assert result == [], "User A must not see integrations from workspace-2"


# ── Domain Shield ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_domain_shield_rejects_unconnected_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /v1/domain-shield/{domain}/status rejects a domain not connected to the workspace."""
    from data_platform.api.routers.app_routes import check_domain_shield_status

    captured, query = _tracking_query({})
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    with pytest.raises(HTTPException) as exc_info:
        await check_domain_shield_status("foreign-domain.test", refresh=False, current_user=USER_A)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_dmarc_reports_reject_foreign_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /v1/domain-shield/{domain}/dmarc-reports rejects a foreign domain."""
    from data_platform.api.routers.app_routes import get_dmarc_report_summary

    captured, query = _tracking_query({})
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    with pytest.raises(HTTPException) as exc_info:
        await get_dmarc_report_summary("foreign-domain.test", USER_A)

    assert exc_info.value.status_code == 404


# ── Admin Authorization ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_runtime_health_rejects_customer() -> None:
    """GET /v1/admin/runtime-health rejects non-admin users."""
    from data_platform.api.routers.app_routes import get_admin_runtime_health

    with pytest.raises(HTTPException) as exc_info:
        await get_admin_runtime_health(USER_A)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_overview_rejects_customer() -> None:
    """GET /v1/admin/overview rejects non-admin users."""
    from data_platform.api.routers.app_routes import get_admin_overview

    with pytest.raises(HTTPException) as exc_info:
        await get_admin_overview(USER_A)

    assert exc_info.value.status_code == 403


# ── Extra User-Scoped Isolation Tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_kpis_are_workspace_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /v1/stats/kpi scopes event query to workspace_id."""
    captured, query = _tracking_query(
        {
            "workspace-2": [{"label_verdict": "phishing", "cnt": 10}],
        }
    )
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    async def mock_count(ws: str) -> int:
        return 5 if ws == "workspace-2" else 0

    monkeypatch.setattr(app_routes, "_workspace_threat_count", mock_count)

    session = MagicMock()
    result = await get_kpis(session=session, current_user=USER_A)

    assert result["threats_phishing_count"] == 0, "Alice must not see Bob's threats in KPI stats"
    assert any("workspace-1" in params for _, params in captured)


@pytest.mark.asyncio
async def test_cloudflare_token_retrieval_is_workspace_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /v1/integrations/cloudflare/token returns configured only for caller's workspace."""
    captured: list[tuple[str, tuple[Any, ...]]] = []

    async def mock_query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        captured.append((sql, params))
        if "workspace-2" in params:
            return [{"api_token": "token-b"}]
        return []

    monkeypatch.setattr(integrations, "_async_query", mock_query)
    monkeypatch.setattr(integrations, "_ensure_tables", lambda: None)

    result = await get_workspace_cloudflare_token(USER_A)
    assert result == {"configured": False}
    assert any("workspace-1" in params for _, params in captured)


@pytest.mark.asyncio
async def test_cloudflare_token_deletion_is_workspace_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DELETE /v1/integrations/cloudflare/token scopes deletions to workspace_id."""
    captured: list[tuple[str, tuple[Any, ...]]] = []

    async def mock_query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        captured.append((sql, params))
        return []

    monkeypatch.setattr(integrations, "_async_query", mock_query)

    result = await delete_workspace_cloudflare_token(USER_A)
    assert result == {"status": "deleted"}
    for _, params in captured:
        assert "workspace-1" in params
