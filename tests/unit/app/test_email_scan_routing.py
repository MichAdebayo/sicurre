"""Mail that is not the customer's never enters their journal or quarantine.

vinse.app and sicurre.com shared one Worker, so a Loops login link sent to
michael@sicurre.com was scanned, quarantined and alerted under vinse.app, and
Sicurre's own alert emails were quarantined as phishing. The scan route now
delivers such mail untouched before any model call or database write.
"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.requests import Request

from data_platform.api.routers import email_scan
from data_platform.api.routers.email_scan import (
    EmailScanRequest,
    _is_sicurre_notification,
    _recipient_outside_zone,
    scan_email,
    upload_quarantine_content,
)

_INTEGRATION = {
    "id": "integration-1",
    "user_email": "owner@vinse.test",
    "workspace_id": "workspace-1",
    "workspace_member_user_id": "user-1",
    "zone_name": "vinse.test",
    "status": "active",
}

_CLOUDFLARE_PASS_SICURRE = (
    "Received: from mail.loops.so by cloudflare-email.net\r\n"
    "ARC-Authentication-Results: i=1; mx.cloudflare.net; dkim=pass header.d=mail.sicurre.com\r\n"
    "Authentication-Results: mx.cloudflare.net;\r\n"
    " dkim=pass header.d=mail.sicurre.com header.s=loops header.b=abc;\r\n"
    " spf=pass smtp.mailfrom=envelope.mail.sicurre.com\r\n"
    "From: Sicurre <no-reply@mail.sicurre.com>\r\n"
    "Subject: Menace interceptee\r\n"
    "\r\n\r\n"
    "Bonjour Michael"
)


def _wire(
    monkeypatch: pytest.MonkeyPatch, rules: list[dict[str, Any]]
) -> list[tuple[str, tuple[Any, ...]]]:
    writes: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        writes.append((sql, params))
        if "FROM cloudflare_integration" in sql:
            return [dict(_INTEGRATION)]
        if "FROM app_security_rule" in sql:
            return rules
        if 'SELECT name FROM "user"' in sql:
            return [{"name": "Owner"}]
        return []

    async def no_alert(**_: Any) -> None:
        return None

    def no_model():
        raise AssertionError("the model must not be called")

    monkeypatch.setattr(email_scan, "ensure_runtime_tables", lambda: None)
    monkeypatch.setattr(email_scan, "_async_query", query)
    monkeypatch.setattr(email_scan, "send_loops_transactional", no_alert)
    monkeypatch.setattr(email_scan, "get_inference_client", no_model)
    monkeypatch.setattr(email_scan, "perf_counter", lambda: 10.0)
    return writes


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/email/scan",
            "headers": [],
            "client": ("127.0.0.1", 4000),
        }
    )


def _stored(writes: list[tuple[str, tuple[Any, ...]]]) -> list[str]:
    return [sql for sql, _ in writes if sql.lstrip().upper().startswith(("INSERT", "UPDATE"))]


@pytest.mark.asyncio
async def test_mail_for_another_domain_is_delivered_without_scanning_or_storing(
    monkeypatch,
) -> None:
    """The Loops login link to michael@sicurre.com that landed in vinse.app's quarantine."""
    writes = _wire(monkeypatch, rules=[])

    response = await scan_email(
        _request(),
        EmailScanRequest(
            message_id="m-1",
            sender="x@envelope.mail.loops.so",
            subject="[Loops] Login link",
            recipient="Michael@Sicurre.com",
            text="Click to sign in",
        ),
        x_sicurre_secret="worker-secret",
    )

    assert response.verdict == "safe"
    assert response.quarantine_id is None
    assert _stored(writes) == []
    assert len(writes) == 1, "only the integration lookup may run"


@pytest.mark.asyncio
@pytest.mark.parametrize("recipient", ["owner@vinse.test", "team@mail.vinse.test", ""])
async def test_mail_for_the_zone_its_subdomains_or_without_recipient_is_still_scanned(
    monkeypatch, recipient
) -> None:
    """A blocklist rule short-circuits the model, so reaching quarantine proves the scan ran."""
    writes = _wire(monkeypatch, rules=[{"rule_type": "blocklist", "pattern": "evil.test"}])

    response = await scan_email(
        _request(),
        EmailScanRequest(
            message_id="m-2",
            sender="attacker@evil.test",
            subject="Urgent",
            recipient=recipient,
            text="Pay now",
        ),
        x_sicurre_secret="worker-secret",
    )

    assert response.verdict == "quarantine"
    assert any("INSERT INTO app_quarantine_item" in sql for sql in _stored(writes))


@pytest.mark.asyncio
async def test_a_sicurre_notification_signed_for_mail_sicurre_com_is_delivered_unscanned(
    monkeypatch,
) -> None:
    writes = _wire(monkeypatch, rules=[{"rule_type": "blocklist", "pattern": "mail.sicurre.com"}])

    response = await scan_email(
        _request(),
        EmailScanRequest(
            message_id="m-3",
            sender="bounce@envelope.mail.sicurre.com",
            subject="Menace",
            recipient="owner@vinse.test",
            text=_CLOUDFLARE_PASS_SICURRE,
        ),
        x_sicurre_secret="worker-secret",
    )

    assert response.verdict == "safe"
    assert _stored(writes) == []


@pytest.mark.asyncio
async def test_a_forged_sicurre_authentication_header_is_not_trusted(monkeypatch) -> None:
    """Cloudflare's own result comes first; a header the sender added below it counts for nothing."""
    forged = (
        "Authentication-Results: mx.cloudflare.net; dkim=pass header.d=evil.test\n"
        "Authentication-Results: mx.cloudflare.net; dkim=pass header.d=mail.sicurre.com\n"
        "\n\nPay now"
    )
    writes = _wire(monkeypatch, rules=[{"rule_type": "blocklist", "pattern": "evil.test"}])

    response = await scan_email(
        _request(),
        EmailScanRequest(
            message_id="m-4",
            sender="attacker@evil.test",
            subject="Menace",
            recipient="owner@vinse.test",
            text=forged,
        ),
        x_sicurre_secret="worker-secret",
    )

    assert response.verdict == "quarantine"
    assert any("INSERT INTO app_quarantine_item" in sql for sql in _stored(writes))


@pytest.mark.parametrize(
    ("text", "trusted"),
    [
        (_CLOUDFLARE_PASS_SICURRE, True),
        (
            "Authentication-Results: mx.cloudflare.net; dkim=pass header.d=mail.sicurre.com.evil.test\n\nx",
            False,
        ),
        (
            "Authentication-Results: mx.cloudflare.net; dkim=fail header.d=mail.sicurre.com\n\nx",
            False,
        ),
        (
            "ARC-Authentication-Results: i=1; mx.cloudflare.net; dkim=pass header.d=mail.sicurre.com\n\nx",
            False,
        ),
        ("Authentication-Results: mx.evil.test; dkim=pass header.d=mail.sicurre.com\n\nx", False),
        (
            "Bonjour\n\nAuthentication-Results: mx.cloudflare.net; dkim=pass header.d=mail.sicurre.com",
            False,
        ),
        ("", False),
    ],
)
def test_only_cloudflares_own_dkim_pass_for_mail_sicurre_com_is_trusted(
    text: str, trusted: bool
) -> None:
    assert _is_sicurre_notification(text) is trusted


@pytest.mark.parametrize(
    ("recipient", "zone", "outside"),
    [
        ("michael@sicurre.com", "vinse.app", True),
        ("<Owner@Vinse.App>", "vinse.app", False),
        ("a@mail.vinse.app", "vinse.app", False),
        ("a@notvinse.app", "vinse.app", True),
        ("", "vinse.app", False),
        ("michael@sicurre.com", "", False),
    ],
)
def test_the_recipient_check_accepts_the_zone_and_its_subdomains_only(
    recipient: str, zone: str, outside: bool
) -> None:
    assert _recipient_outside_zone(recipient, zone) is outside


@pytest.mark.asyncio
async def test_uploading_the_raw_mime_rebuilds_a_readable_masked_preview(monkeypatch) -> None:
    raw = (
        b"Received: from mail.example by cloudflare-email.net\r\n"
        b"From: Service <billing@evil.test>\r\n"
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"Content-Transfer-Encoding: quoted-printable\r\n"
        b"\r\n"
        b"Un remboursement de 312,45 EUR vous attend. =C3=89crivez =C3=A0 victim@example.test.\r\n"
    )
    writes: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        writes.append((sql, params))
        if "FROM cloudflare_integration" in sql:
            return [{"workspace_id": "workspace-1", "zone_name": "vinse.test"}]
        if "SELECT raw_storage_uri, raw_content_hash FROM app_quarantine_item" in sql:
            return [{"raw_storage_uri": None, "raw_content_hash": None}]
        return []

    class Stored:
        storage_uri = "file:///tmp/item-1.eml"
        content_hash = "hash"
        size_bytes = len(raw)

    class Store:
        async def write(self, **_: Any) -> Stored:
            return Stored()

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": raw, "more_body": False}

    monkeypatch.setattr(email_scan, "_async_query", query)
    monkeypatch.setattr(email_scan, "build_quarantine_store", lambda _settings: Store())
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/email/quarantine/item-1/content",
            "headers": [],
            "client": ("127.0.0.1", 4000),
        },
        receive,
    )

    result = await upload_quarantine_content("item-1", request, x_sicurre_secret="worker-secret")

    assert result == {"status": "stored", "idempotent": False}
    sql, params = next((sql, params) for sql, params in writes if "SET body_text = ?" in sql)
    assert params[0] == "Un remboursement de 312,45 EUR vous attend. Écrivez à [EMAIL]."
    assert params[1:] == ("item-1", "workspace-1", "vinse.test")
