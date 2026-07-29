"""Boundary, malformed-input, and unavailable-dependency tests for public API endpoints.

These tests verify that the API rejects bad input with appropriate HTTP error
codes, validates field constraints, and returns useful error messages when
downstream dependencies are unavailable.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from data_platform.api.auth import AuthUser
from data_platform.api.routers import app_routes, integrations
from data_platform.api.routers.app_routes import (
    FeedbackCreate,
    SecurityRuleCreate,
    StatusUpdate,
    SupportRequestCreate,
    UpdateProfileRequest,
)
from data_platform.api.routers.integrations import EmailScanRequest

# ── Fixtures ─────────────────────────────────────────────────────────────────

_USER = AuthUser(
    id="user-1",
    email="owner@example.test",
    display_name="Owner",
    role="owner",
    workspace_id="workspace-1",
    workspace_name="Workspace",
    is_platform_admin=False,
)


def _limiter_request() -> Request:
    """Build a minimal ASGI request that satisfies SlowAPI's key function."""
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "client": ("127.0.0.1", 4000),
        }
    )


# ── Email Scan: Missing / Invalid Secret ─────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_email_rejects_missing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /v1/email/scan rejects when the X-Sicurre-Secret header is absent."""
    monkeypatch.setattr(integrations, "_ensure_tables", lambda: None)

    with pytest.raises(HTTPException) as exc_info:
        await integrations.scan_email(
            request=_limiter_request(),
            payload=EmailScanRequest(subject="Test", sender="a@b.com", text="Hi"),
            x_sicurre_secret=None,
        )

    assert exc_info.value.status_code == 401
    assert "Missing" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_scan_email_rejects_invalid_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /v1/email/scan rejects when the shared secret does not match any integration."""
    monkeypatch.setattr(integrations, "_ensure_tables", lambda: None)

    async def empty_query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(integrations, "_async_query", empty_query)

    with pytest.raises(HTTPException) as exc_info:
        await integrations.scan_email(
            request=_limiter_request(),
            payload=EmailScanRequest(subject="Test", sender="a@b.com", text="Hi"),
            x_sicurre_secret="completely-invalid-secret",
        )

    assert exc_info.value.status_code == 401
    assert "Invalid" in str(exc_info.value.detail)


# ── Email Scan: Inference Unavailable ────────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_email_returns_503_when_inference_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /v1/email/scan returns 503 when the inference API is unreachable."""
    import httpx

    secret = "valid-secret"

    monkeypatch.setattr(integrations, "_ensure_tables", lambda: None)

    call_count = 0
    expected_hash = hashlib.sha256(secret.encode()).hexdigest()

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            assert "shared_secret_hash = ?" in sql
            assert params == (expected_hash,)
            return [
                {
                    "id": "int-1",
                    "user_email": "owner@test",
                    "workspace_id": "workspace-1",
                    "workspace_member_user_id": "user-1",
                    "zone_name": "test.com",
                    "status": "active",
                }
            ]
        # All subsequent queries return empty (no existing quarantine/event, no rules)
        return []

    monkeypatch.setattr(integrations, "_async_query", query)

    # Make httpx.AsyncClient always raise a connection error
    class FailingClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> FailingClient:
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def post(self, *_: Any, **__: Any) -> None:
            raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr("httpx.AsyncClient", FailingClient)

    with pytest.raises(HTTPException) as exc_info:
        await integrations.scan_email(
            request=_limiter_request(),
            payload=EmailScanRequest(subject="Test", sender="a@b.com", text="Body"),
            x_sicurre_secret=secret,
        )

    assert exc_info.value.status_code == 503
    assert "temporarily unavailable" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_scan_email_records_whitelist_stage_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A whitelist decision records why inference was bypassed."""
    writes: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        writes.append((sql, params))
        if "FROM cloudflare_integration" in sql:
            return [
                {
                    "id": "int-1",
                    "user_email": "owner@test",
                    "workspace_id": "workspace-1",
                    "workspace_member_user_id": "user-1",
                    "zone_name": "test.com",
                    "status": "active",
                }
            ]
        if "FROM app_security_rule" in sql:
            return [{"rule_type": "whitelist", "pattern": "trusted.test"}]
        return []

    monkeypatch.setattr(integrations, "_ensure_tables", lambda: None)
    monkeypatch.setattr(integrations, "_async_query", query)

    response = await integrations.scan_email(
        request=_limiter_request(),
        payload=EmailScanRequest(
            subject="Expected message",
            sender="notices@trusted.test",
            text="Routine account notice.",
        ),
        x_sicurre_secret="valid-secret",
    )

    assert response.verdict == "safe"
    insert = next(params for sql, params in writes if "INSERT INTO app_inference_event" in sql)
    assert json.loads(insert[-3]) == {"custom_rule": "legitimate"}
    assert json.loads(insert[-2]) == {
        "custom_rule": {"active": True, "rule_type": "whitelist"}
    }


@pytest.mark.asyncio
async def test_scan_email_persists_ml_stage_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The app audit row retains the bounded ML provider and stage evidence."""
    writes: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        writes.append((sql, params))
        if "FROM cloudflare_integration" in sql:
            return [
                {
                    "id": "int-1",
                    "user_email": "owner@test",
                    "workspace_id": "workspace-1",
                    "workspace_member_user_id": "user-1",
                    "zone_name": "test.com",
                    "status": "active",
                }
            ]
        return []

    class SuccessResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "is_phishing": False,
                "label_verdict": "legitimate",
                "composite_score": 0.04,
                "explanation": "Message cohérent.",
                "llm_provider": "mistral",
                "stage_scores": {"onnx": 0.1, "llm": 0.02},
                "stage_labels": {"onnx": "spam", "llm": "legitimate"},
                "stage_breakdown": {"llm": {"active": True, "provider": "mistral"}},
            }

    class SuccessClient:
        def __init__(self, **_: Any) -> None:
            pass

        async def __aenter__(self) -> SuccessClient:
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def post(self, *_: Any, **__: Any) -> SuccessResponse:
            return SuccessResponse()

    monkeypatch.setattr(integrations, "_ensure_tables", lambda: None)
    monkeypatch.setattr(integrations, "_async_query", query)
    monkeypatch.setattr("httpx.AsyncClient", SuccessClient)

    response = await integrations.scan_email(
        request=_limiter_request(),
        payload=EmailScanRequest(
            message_id="message-1",
            subject="Confirmation",
            sender="events@example.fr",
            text="Inscription confirmée.",
        ),
        x_sicurre_secret="valid-secret",
    )

    assert response.label == "legitimate"
    inserted = next(
        params for sql, params in writes if "INSERT INTO app_inference_event" in sql
    )
    assert inserted[14] == "mistral"
    assert inserted[20] == '{"llm":0.02,"onnx":0.1}'
    assert inserted[21] == '{"llm":"legitimate","onnx":"spam"}'
    assert inserted[22] == '{"llm":{"active":true,"provider":"mistral"}}'


# ── Pydantic Schema Validation ───────────────────────────────────────────────


class TestEmailScanRequestValidation:
    """Verify field constraints on the email scan request schema."""


    def test_rejects_oversized_subject(self) -> None:
        with pytest.raises(ValidationError, match="String should have at most 500"):
            EmailScanRequest(subject="X" * 501, sender="a@b.com", text="Hi")

    def test_rejects_oversized_sender(self) -> None:
        with pytest.raises(ValidationError, match="String should have at most 200"):
            EmailScanRequest(subject="Hi", sender="a" * 201, text="Hi")

    def test_rejects_oversized_text(self) -> None:
        with pytest.raises(ValidationError, match="String should have at most 10000"):
            EmailScanRequest(subject="Hi", sender="a@b.com", text="X" * 10_001)

    def test_accepts_valid_minimal_payload(self) -> None:
        req = EmailScanRequest(subject="", sender="", text="")
        assert req.subject == ""

    def test_defaults_are_safe(self) -> None:
        req = EmailScanRequest()
        assert req.use_llm is True
        assert req.use_virustotal is False


class TestFeedbackValidation:
    """Verify field constraints on the feedback creation schema."""

    def test_rejects_invalid_feedback_type(self) -> None:
        with pytest.raises(ValidationError, match="pattern"):
            FeedbackCreate(
                feedback_type="invalid_type",
                corrected_verdict="phishing",
            )

    def test_rejects_invalid_corrected_verdict(self) -> None:
        with pytest.raises(ValidationError, match="pattern"):
            FeedbackCreate(
                feedback_type="false_positive",
                corrected_verdict="invalid_verdict",
            )

    def test_rejects_oversized_reporter_note(self) -> None:
        with pytest.raises(ValidationError, match="String should have at most 500"):
            FeedbackCreate(
                feedback_type="false_positive",
                corrected_verdict="legitimate",
                reporter_note="X" * 501,
            )

    def test_rejects_oversized_event_id(self) -> None:
        with pytest.raises(ValidationError, match="String should have at most 120"):
            FeedbackCreate(
                event_id="X" * 121,
                feedback_type="false_positive",
                corrected_verdict="legitimate",
            )

    def test_accepts_all_valid_feedback_types(self) -> None:
        for ft in ("false_negative", "false_positive", "true_positive", "true_negative"):
            fb = FeedbackCreate(feedback_type=ft, corrected_verdict="phishing")
            assert fb.feedback_type == ft

    def test_accepts_all_valid_corrected_verdicts(self) -> None:
        for cv in ("phishing", "spam", "legitimate", "quarantine"):
            fb = FeedbackCreate(feedback_type="false_positive", corrected_verdict=cv)
            assert fb.corrected_verdict == cv


class TestSupportRequestValidation:
    """Verify field constraints on support request creation."""

    def test_rejects_short_name(self) -> None:
        with pytest.raises(ValidationError, match="String should have at least 2"):
            SupportRequestCreate(
                requester_name="A",
                requester_email="a@b.com",
                category="other",
                message="This is a valid message for support.",
            )

    def test_rejects_invalid_email(self) -> None:
        with pytest.raises(ValidationError, match="pattern"):
            SupportRequestCreate(
                requester_name="Alice",
                requester_email="not-an-email",
                category="other",
                message="This is a valid message for support.",
            )

    def test_rejects_invalid_category(self) -> None:
        with pytest.raises(ValidationError, match="pattern"):
            SupportRequestCreate(
                requester_name="Alice",
                requester_email="a@b.com",
                category="hacking",
                message="This is a valid message for support.",
            )

    def test_rejects_short_message(self) -> None:
        with pytest.raises(ValidationError, match="String should have at least 10"):
            SupportRequestCreate(
                requester_name="Alice",
                requester_email="a@b.com",
                category="other",
                message="Short",
            )

    def test_rejects_oversized_message(self) -> None:
        with pytest.raises(ValidationError, match="String should have at most 4000"):
            SupportRequestCreate(
                requester_name="Alice",
                requester_email="a@b.com",
                category="other",
                message="X" * 4001,
            )


class TestProfileValidation:
    """Verify field constraints on profile update."""

    def test_rejects_short_display_name(self) -> None:
        with pytest.raises(ValidationError, match="String should have at least 2"):
            UpdateProfileRequest(display_name="A")

    def test_rejects_long_display_name(self) -> None:
        with pytest.raises(ValidationError, match="String should have at most 120"):
            UpdateProfileRequest(display_name="A" * 121)


class TestStatusUpdateValidation:
    """Verify that threat status only accepts valid values."""

    @pytest.mark.asyncio
    async def test_rejects_invalid_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """POST /v1/threats/{id}/status rejects invalid status values at the handler level."""
        from data_platform.api.routers.app_routes import update_threat_status

        with pytest.raises(HTTPException) as exc_info:
            await update_threat_status("threat-1", StatusUpdate(status="hacked"), _USER)

        assert exc_info.value.status_code == 400


class TestSecurityRuleValidation:
    """Verify normalization and validation on security rules."""

    def test_pattern_is_lowercased_and_stripped(self) -> None:
        rule = SecurityRuleCreate(rule_type="blocklist", pattern="  ADMIN@Evil.COM  ")
        assert rule.pattern == "admin@evil.com"

    def test_whitespace_only_pattern_is_rejected(self) -> None:
        """Whitespace-only patterns are stripped then rejected by min_length."""
        with pytest.raises(ValidationError, match="string_too_short"):
            SecurityRuleCreate(rule_type="blocklist", pattern="   ")


# ── Duplicate Feedback Idempotency ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_feedback_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /v1/feedback returns 409 on duplicate submission."""
    from data_platform.api.routers.app_routes import create_feedback

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if "INSERT INTO app_feedback" in sql:
            raise Exception("UNIQUE constraint failed: app_feedback.event_id")
        return []

    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    with pytest.raises(HTTPException) as exc_info:
        await create_feedback(
            FeedbackCreate(feedback_type="false_positive", corrected_verdict="legitimate"),
            _USER,
        )

    assert exc_info.value.status_code == 409
    assert "already submitted" in str(exc_info.value.detail).lower()
