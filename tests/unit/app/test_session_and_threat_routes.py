"""Direct-call tests for the session helpers, the profile patch, and the threat routes.

The route functions are awaited directly with the auth and runtime query layers
monkeypatched, so each test pins one SQL branch without an HTTP client or a database.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from fastapi import HTTPException

from data_platform.api import workspace_scope
from data_platform.api.auth import AuthUser
from data_platform.api.routers import session, threats
from data_platform.api.routers.session import (
    UpdateProfileRequest,
    patch_profile,
)
from data_platform.api.routers.threats import (
    FeedbackCreate,
    StatusUpdate,
    create_feedback,
    update_threat_status,
)
from data_platform.api.workspace_scope import (
    workspace_has_cloudflare_integration,
    workspace_threat_count,
)

_USER = AuthUser(
    id="user-1",
    email="owner@example.test",
    display_name="Owner",
    role="owner",
    workspace_id="workspace-1",
    workspace_name="Workspace",
    is_platform_admin=False,
)
_DOMAIN = "example.test"

_THREAT_ROW = {
    "id": "threat-1",
    "message_id": "threat-1",
    "subject": "Urgent invoice",
    "sender": "billing@evil.test",
    "body_preview": "Pay now",
    "verdict": "phishing",
    "confidence": 0.97,
    "received_at": "2026-09-01T10:00:00Z",
    "status": "trashed",
}


def _fragment_query(
    responses: dict[str, list[dict[str, Any]] | Exception],
) -> tuple[list[tuple[str, tuple[Any, ...]]], Any]:
    """Return (captured, query) where query answers by the first SQL fragment it matches.

    A fragment mapped to an exception raises it so the failure branches can be driven.
    """
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


async def _allow_domain(_domain: str, _workspace_id: str) -> None:
    return None


@pytest.fixture
def _owned_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workspace_scope, "require_workspace_domain", _allow_domain)


# ── Session helpers ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_threat_count_is_scoped_to_the_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured, query = _fragment_query({"COUNT(*)": [{"count": "7"}]})
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    count = await workspace_threat_count("workspace-1")

    assert count == 7
    sql, params = captured[0]
    assert "WHERE workspace_id = ?" in sql
    assert "domain" not in sql
    assert params == ("workspace-1",)


@pytest.mark.asyncio
async def test_the_threat_count_adds_the_domain_predicate_when_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured, query = _fragment_query({"COUNT(*)": [{"count": 3}]})
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    count = await workspace_threat_count("workspace-1", _DOMAIN)

    assert count == 3
    sql, params = captured[0]
    assert "AND lower(domain) = lower(?)" in sql
    assert params == ("workspace-1", _DOMAIN)


@pytest.mark.asyncio
async def test_the_threat_count_is_zero_when_no_row_comes_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _captured, query = _fragment_query({})
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    assert await workspace_threat_count("workspace-1") == 0


@pytest.mark.asyncio
async def test_a_live_cloudflare_integration_is_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured, query = _fragment_query({"FROM cloudflare_integration": [{"found": 1}]})
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    assert await workspace_has_cloudflare_integration("workspace-1") is True
    sql, params = captured[0]
    assert "status IN ('pending_verification', 'active', 'provisioning')" in sql
    assert params == ("workspace-1",)


@pytest.mark.asyncio
async def test_a_workspace_without_integration_reports_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _captured, query = _fragment_query({})
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    assert await workspace_has_cloudflare_integration("workspace-1") is False


# ── Profile patch ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patching_the_profile_updates_both_tables_and_returns_the_new_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The session payload must reflect the new name without a re-login."""
    captured, query = _fragment_query({})
    monkeypatch.setattr(session, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    async def threat_count(workspace_id: str, domain: str | None = None) -> int:
        assert workspace_id == "workspace-1"
        return 0

    async def has_integration(workspace_id: str) -> bool:
        assert workspace_id == "workspace-1"
        return False

    monkeypatch.setattr(workspace_scope, "workspace_threat_count", threat_count)

    monkeypatch.setattr(session, "workspace_threat_count", threat_count)
    monkeypatch.setattr(workspace_scope, "workspace_has_cloudflare_integration", has_integration)
    monkeypatch.setattr(session, "workspace_has_cloudflare_integration", has_integration)

    result = await patch_profile(
        payload=UpdateProfileRequest(display_name="  New Owner  "),
        current_user=_USER,
    )

    assert len(captured) == 2
    user_sql, user_params = captured[0]
    assert 'UPDATE "user" SET name = ?' in user_sql
    assert user_params[0] == "New Owner"
    assert user_params[2] == "user-1"
    membership_sql, membership_params = captured[1]
    assert "UPDATE app_workspace_membership SET display_name = ?" in membership_sql
    assert membership_params[0] == "New Owner"
    assert membership_params[2] == "user-1"
    assert user_params[1] == membership_params[1]

    assert result["display_name"] == "New Owner"
    assert result["id"] == "user-1"
    assert result["workspace_id"] == "workspace-1"
    assert result["has_cloudflare_integration"] is False
    assert result["threat_count"] == 0
    assert result["onboarding_required"] is True
    assert isinstance(result["sla_latency_ms"], int)


# ── Threat status ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.usefixtures("_owned_domain")
async def test_updating_the_status_of_an_unknown_threat_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured, query = _fragment_query({})
    monkeypatch.setattr(threats, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    with pytest.raises(HTTPException) as exc_info:
        await update_threat_status(
            id="missing",
            payload=StatusUpdate(status="trashed"),
            domain=_DOMAIN,
            current_user=_USER,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Threat not found"
    update_sql, update_params = captured[0]
    assert update_sql.startswith("UPDATE app_inference_event SET is_deleted = ?")
    assert update_params[0] == 1
    assert update_params[3:] == ("missing", "workspace-1", _DOMAIN)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_owned_domain")
async def test_a_phishing_threat_status_update_returns_the_unmasked_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _captured, query = _fragment_query({"SELECT id, id AS message_id": [_THREAT_ROW]})
    monkeypatch.setattr(threats, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await update_threat_status(
        id="threat-1",
        payload=StatusUpdate(status="trashed"),
        domain=_DOMAIN,
        current_user=_USER,
    )

    assert result["content_redacted"] is False
    assert result["subject"] == "Urgent invoice"
    assert result["privacy_reference"] == "MSG-THREAT1"
    assert result["status"] == "trashed"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_owned_domain")
async def test_a_legitimate_threat_status_update_masks_the_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = {**_THREAT_ROW, "verdict": "legitimate", "status": None}
    _captured, query = _fragment_query({"SELECT id, id AS message_id": [row]})
    monkeypatch.setattr(threats, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await update_threat_status(
        id="threat-1",
        payload=StatusUpdate(status="restored"),
        domain=_DOMAIN,
        current_user=_USER,
    )

    assert result["content_redacted"] is True
    assert result["subject"] == "[Masqué par Sicurre]"
    assert result["sender"] == "[Masqué par Sicurre]"
    assert result["body_preview"] == "[Masqué par Sicurre]"
    assert result["status"] == "active"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_owned_domain")
async def test_a_database_failure_during_status_update_is_logged_and_becomes_a_500(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The raw driver error must not leak to the client, only to the log."""
    _captured, query = _fragment_query(
        {"UPDATE app_inference_event": RuntimeError("disk I/O error")}
    )
    monkeypatch.setattr(threats, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    with caplog.at_level(logging.ERROR, logger=threats.logger.name):
        with pytest.raises(HTTPException) as exc_info:
            await update_threat_status(
                id="threat-1",
                payload=StatusUpdate(status="active"),
                domain=_DOMAIN,
                current_user=_USER,
            )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Unable to update threat status"
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert "Threat status update failed" in caplog.text
    assert "disk I/O error" in caplog.text


# ── Feedback ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.usefixtures("_owned_domain")
async def test_a_feedback_on_an_unknown_event_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured, query = _fragment_query({})
    monkeypatch.setattr(threats, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    with pytest.raises(HTTPException) as exc_info:
        await create_feedback(
            payload=FeedbackCreate(
                event_id="missing",
                feedback_type="false_positive",
                corrected_verdict="legitimate",
            ),
            domain=_DOMAIN,
            current_user=_USER,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Linked event not found"
    assert len(captured) == 1
    assert "SELECT id, safety_verdict" in captured[0][0]
    assert captured[0][1] == ("missing", "workspace-1", _DOMAIN)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_owned_domain")
async def test_a_duplicate_feedback_is_reported_as_a_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _captured, query = _fragment_query(
        {"INSERT INTO app_feedback": Exception("UNIQUE constraint failed: app_feedback.id")}
    )
    monkeypatch.setattr(threats, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    with pytest.raises(HTTPException) as exc_info:
        await create_feedback(
            payload=FeedbackCreate(feedback_type="true_positive", corrected_verdict="phishing"),
            domain=_DOMAIN,
            current_user=_USER,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Feedback already submitted"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_owned_domain")
async def test_any_other_insert_failure_becomes_a_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _captured, query = _fragment_query(
        {"INSERT INTO app_feedback": RuntimeError("database is locked")}
    )
    monkeypatch.setattr(threats, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    with pytest.raises(HTTPException) as exc_info:
        await create_feedback(
            payload=FeedbackCreate(feedback_type="true_negative", corrected_verdict="legitimate"),
            domain=_DOMAIN,
            current_user=_USER,
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Could not record feedback"
    assert isinstance(exc_info.value.__cause__, RuntimeError)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_owned_domain")
async def test_a_false_negative_report_marks_the_event_as_reported_false_negative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured, query = _fragment_query(
        {"SELECT id, safety_verdict": [{"id": "event-1", "safety_verdict": "safe"}]}
    )
    monkeypatch.setattr(threats, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await create_feedback(
        payload=FeedbackCreate(
            event_id="event-1",
            feedback_type="false_negative",
            corrected_verdict="phishing",
            reporter_note="  it asked for my password  ",
        ),
        domain=_DOMAIN,
        current_user=_USER,
    )

    assert [sql.split()[0] for sql, _params in captured] == ["SELECT", "INSERT", "UPDATE"]
    insert_sql, insert_params = captured[1]
    assert "INSERT INTO app_feedback" in insert_sql
    assert insert_params[1:9] == (
        "workspace-1",
        "user-1",
        "event-1",
        "false_negative",
        "safe",
        "phishing",
        "it asked for my password",
        result["created_at"],
    )
    update_sql, update_params = captured[2]
    assert "SET override_verdict = ?, overridden_at = ?" in update_sql
    assert update_params == (
        "reported_false_negative",
        result["created_at"],
        "event-1",
        "workspace-1",
        _DOMAIN,
    )
    assert result["event_id"] == "event-1"
    assert result["original_verdict"] == "safe"
    assert result["corrected_verdict"] == "phishing"
    assert result["id"] == insert_params[0]


@pytest.mark.asyncio
@pytest.mark.usefixtures("_owned_domain")
async def test_a_false_positive_report_marks_the_event_as_reported_false_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured, query = _fragment_query(
        {"SELECT id, safety_verdict": [{"id": "event-2", "safety_verdict": "phishing"}]}
    )
    monkeypatch.setattr(threats, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await create_feedback(
        payload=FeedbackCreate(
            event_id="event-2",
            feedback_type="false_positive",
            corrected_verdict="legitimate",
        ),
        domain=_DOMAIN,
        current_user=_USER,
    )

    update_sql, update_params = captured[2]
    assert "UPDATE app_inference_event" in update_sql
    assert update_params[0] == "reported_false_positive"
    assert update_params[2:] == ("event-2", "workspace-1", _DOMAIN)
    assert captured[1][1][7] is None
    assert result["original_verdict"] == "phishing"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_owned_domain")
async def test_a_feedback_without_an_event_skips_the_override_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured, query = _fragment_query({})
    monkeypatch.setattr(threats, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await create_feedback(
        payload=FeedbackCreate(feedback_type="true_positive", corrected_verdict="phishing"),
        domain=_DOMAIN,
        current_user=_USER,
    )

    assert [sql.split()[0] for sql, _params in captured] == ["INSERT"]
    assert result["event_id"] is None
    assert result["original_verdict"] is None
