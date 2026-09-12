"""The Worker-facing routes: idempotent replies, rule matching, custody, failure paths."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from data_platform.api.routers import email_scan
from data_platform.api.routers.email_scan import (
    EmailScanRequest,
    scan_email,
    upload_quarantine_content,
)

INTEGRATION = {
    "id": "integration-1",
    "user_email": "owner@example.test",
    "workspace_id": "workspace-1",
    "workspace_member_user_id": "user-1",
    "zone_name": "example.test",
    "status": "active",
}


def _request(method: str = "POST", body: bytes = b"") -> Request:
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        chunk = b"" if sent else body
        sent = True
        return {"type": "http.request", "body": chunk, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": method,
            "path": "/v1/email/scan",
            "headers": [],
            "client": ("127.0.0.1", 4000),
        },
        receive,
    )


def _payload(**overrides: Any) -> EmailScanRequest:
    fields: dict[str, Any] = {
        "message_id": "message-1",
        "sender": "attacker@example.test",
        "subject": "Urgent",
        "text": "Body",
    }
    fields.update(overrides)
    return EmailScanRequest(**fields)


def _queries(
    monkeypatch: pytest.MonkeyPatch,
    answers: dict[str, Any],
    writes: list[tuple[str, tuple[Any, ...]]] | None = None,
) -> None:
    """Answer SELECTs by SQL fragment; a fragment mapped to an exception raises it."""

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if writes is not None:
            writes.append((sql, params))
        for fragment, rows in answers.items():
            if fragment in sql:
                if isinstance(rows, Exception):
                    raise rows
                return rows
        return []

    async def no_notification(**_: Any) -> None:
        return None

    monkeypatch.setattr(email_scan, "ensure_runtime_tables", lambda: None)
    monkeypatch.setattr(email_scan, "_async_query", query)
    monkeypatch.setattr(email_scan, "send_loops_transactional", no_notification)
    monkeypatch.setattr(
        email_scan, "get_inference_client", lambda: pytest.fail("the classifier was called")
    )


@pytest.mark.asyncio
async def test_a_message_already_held_gets_the_same_quarantine_decision(monkeypatch) -> None:
    _queries(
        monkeypatch,
        {
            "FROM cloudflare_integration": [INTEGRATION],
            "FROM app_quarantine_item": [
                {
                    "id": "q-1",
                    "message_id": "evt-1",
                    "safety_verdict": "phishing",
                    "composite_score": 0.97,
                }
            ],
        },
    )

    response = await scan_email(_request(), _payload(), x_sicurre_secret="worker-secret")

    assert (response.verdict, response.label, response.quarantine_id) == (
        "quarantine",
        "phishing",
        "q-1",
    )
    assert response.event_id == "evt-1"
    assert response.explanation == "Existing idempotent quarantine decision."


@pytest.mark.asyncio
async def test_a_message_already_judged_gets_the_recorded_verdict(monkeypatch) -> None:
    _queries(
        monkeypatch,
        {
            "FROM cloudflare_integration": [INTEGRATION],
            "FROM app_inference_event": [
                {
                    "id": "evt-1",
                    "safety_verdict": "safe",
                    "label_verdict": "legitimate",
                    "composite_score": 0.12,
                    "explanation": "",
                    "latency_ms": 0,
                }
            ],
        },
    )

    response = await scan_email(_request(), _payload(), x_sicurre_secret="worker-secret")

    assert (response.verdict, response.label, response.score) == ("safe", "legitimate", 0.12)
    assert response.explanation == "Existing idempotent decision."
    assert response.latency_ms is None


@pytest.mark.parametrize(
    "rules",
    [
        [
            {"rule_type": "blocklist", "pattern": "other.test"},
            {"rule_type": "blocklist", "pattern": "@example.test"},
        ],
        [{"rule_type": "blocklist", "pattern": "attacker@example.test"}],
    ],
    ids=["domain-suffix-after-a-miss", "exact-address"],
)
@pytest.mark.asyncio
async def test_blocklist_patterns_match_a_domain_suffix_or_an_exact_address(
    monkeypatch, rules: list[dict[str, str]]
) -> None:
    """The customer's blocklist decides before any model is consulted."""
    writes: list[tuple[str, tuple[Any, ...]]] = []
    _queries(
        monkeypatch,
        {
            "FROM cloudflare_integration": [INTEGRATION],
            "FROM app_security_rule": rules,
            'SELECT name FROM "user"': [{"name": None}],
        },
        writes,
    )
    sent: list[dict[str, Any]] = []

    async def notification(**kwargs: Any) -> None:
        sent.append(kwargs)

    monkeypatch.setattr(email_scan, "send_loops_transactional", notification)

    response = await scan_email(_request(), _payload(), x_sicurre_secret="worker-secret")

    assert (response.verdict, response.label, response.score) == ("quarantine", "phishing", 1.0)
    assert response.explanation == "Blocked by custom security blocklist rule."
    assert any("INSERT INTO app_quarantine_item" in sql for sql, _ in writes)
    # No name on the account: the alert still goes out, with the neutral greeting.
    assert sent[0]["data_variables"]["firstName"] == "Utilisateur"


@pytest.mark.asyncio
async def test_a_customer_who_opted_out_is_not_notified(monkeypatch) -> None:
    writes: list[tuple[str, tuple[Any, ...]]] = []
    _queries(
        monkeypatch,
        {
            "FROM cloudflare_integration": [INTEGRATION],
            "FROM app_security_rule": [{"rule_type": "blocklist", "pattern": "example.test"}],
        },
        writes,
    )
    monkeypatch.setattr(email_scan, "notification_is_allowed", lambda *_: False)
    monkeypatch.setattr(
        email_scan, "send_loops_transactional", lambda **_: pytest.fail("notified anyway")
    )

    response = await scan_email(_request(), _payload(), x_sicurre_secret="worker-secret")

    assert response.verdict == "quarantine"
    assert not any('SELECT name FROM "user"' in sql for sql, _ in writes)


@pytest.mark.asyncio
async def test_a_failed_quarantine_write_is_logged_and_the_verdict_still_returned(
    monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Holding the message failed, so the Worker is told phishing, not quarantine."""
    _queries(
        monkeypatch,
        {
            "FROM cloudflare_integration": [INTEGRATION],
            "FROM app_security_rule": [{"rule_type": "blocklist", "pattern": "example.test"}],
            "INSERT INTO app_quarantine_item": RuntimeError("quarantine table locked"),
        },
    )

    with caplog.at_level(logging.WARNING):
        response = await scan_email(_request(), _payload(), x_sicurre_secret="worker-secret")

    assert response.verdict == "phishing"
    assert "Could not quarantine phishing email" in caplog.text


@pytest.mark.asyncio
async def test_the_first_successful_scan_activates_a_pending_integration(monkeypatch) -> None:
    writes: list[tuple[str, tuple[Any, ...]]] = []
    _queries(
        monkeypatch,
        {
            "FROM cloudflare_integration": [{**INTEGRATION, "status": "pending_verification"}],
            "FROM app_security_rule": [{"rule_type": "blocklist", "pattern": "example.test"}],
        },
        writes,
    )

    await scan_email(_request(), _payload(), x_sicurre_secret="worker-secret")

    activation = [sql for sql, _ in writes if "SET status = 'active'" in sql]
    assert len(activation) == 1


@pytest.mark.asyncio
async def test_a_failed_audit_write_never_fails_the_scan(
    monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    _queries(
        monkeypatch,
        {
            "FROM cloudflare_integration": [INTEGRATION],
            "FROM app_security_rule": [{"rule_type": "blocklist", "pattern": "example.test"}],
            "INSERT INTO app_inference_event": RuntimeError("journal unavailable"),
        },
    )

    with caplog.at_level(logging.WARNING):
        response = await scan_email(_request(), _payload(), x_sicurre_secret="worker-secret")

    assert response.verdict == "quarantine"
    assert "Could not persist audit log" in caplog.text


# --- MIME custody -----------------------------------------------------------


def _custody(
    monkeypatch: pytest.MonkeyPatch, item: dict[str, Any] | None, *, known_secret: bool = True
) -> None:
    _queries(
        monkeypatch,
        {
            "FROM cloudflare_integration": (
                [{"workspace_id": "workspace-1", "zone_name": "example.test"}]
                if known_secret
                else []
            ),
            "FROM app_quarantine_item": [item] if item else [],
        },
    )
    monkeypatch.setattr(
        email_scan, "get_settings", lambda: SimpleNamespace(quarantine_max_message_bytes=32)
    )


async def _upload(secret: str | None, body: bytes) -> dict[str, Any]:
    return await upload_quarantine_content("item-1", _request("PUT", body), x_sicurre_secret=secret)


@pytest.mark.asyncio
async def test_custody_refuses_a_missing_or_unknown_secret(monkeypatch) -> None:
    _custody(monkeypatch, None, known_secret=False)

    with pytest.raises(HTTPException) as missing:
        await _upload(None, b"From: a\r\n\r\nBody")
    with pytest.raises(HTTPException) as unknown:
        await _upload("worker-secret", b"From: a\r\n\r\nBody")

    assert (missing.value.status_code, unknown.value.status_code) == (401, 401)
    assert "Missing" in missing.value.detail and "Invalid" in unknown.value.detail


@pytest.mark.asyncio
async def test_custody_needs_a_held_item_and_a_body_within_the_limit(monkeypatch) -> None:
    _custody(monkeypatch, None)
    with pytest.raises(HTTPException) as no_item:
        await _upload("worker-secret", b"From: a\r\n\r\nBody")
    assert no_item.value.status_code == 404

    _custody(monkeypatch, {"raw_storage_uri": None, "raw_content_hash": None})
    with pytest.raises(HTTPException) as empty:
        await _upload("worker-secret", b"")
    with pytest.raises(HTTPException) as too_large:
        await _upload("worker-secret", b"x" * 33)
    assert (empty.value.status_code, too_large.value.status_code) == (400, 413)


@pytest.mark.asyncio
async def test_custody_is_idempotent_for_the_same_bytes_and_refuses_different_ones(
    monkeypatch,
) -> None:
    import hashlib

    body = b"From: a\r\n\r\nBody"
    _custody(
        monkeypatch,
        {
            "raw_storage_uri": "file:///item.eml",
            "raw_content_hash": hashlib.sha256(body).hexdigest(),
        },
    )
    assert await _upload("worker-secret", body) == {"status": "stored", "idempotent": True}

    with pytest.raises(HTTPException) as conflict:
        await _upload("worker-secret", b"From: a\r\n\r\nOther body")
    assert conflict.value.status_code == 409


@pytest.mark.asyncio
async def test_the_query_seam_delegates_to_the_runtime_engine(monkeypatch) -> None:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    async def engine(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        calls.append((sql, params))
        return [{"ok": 1}]

    monkeypatch.setattr(email_scan, "execute_runtime_query", engine)
    assert await email_scan._async_query("SELECT 1", (1,)) == [{"ok": 1}]
    assert calls == [("SELECT 1", (1,))]
