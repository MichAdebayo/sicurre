"""Tests for workspace-scoped false-negative forwarding."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from data_platform.api.auth import AuthUser
from data_platform.api.routers import reported_email as router
from data_platform.services.reported_email import (
    InvalidReportAlias,
    LocalReportedEmailStore,
    ReportAliasCodec,
    report_address,
    sanitized_evidence,
)

WORKSPACE_ID = "6d4f2f4c-8d7e-4bc1-9c99-8efc9ba19c73"
SECRET = "test-reported-email-alias-secret-32-bytes-minimum"
USER = AuthUser(
    id="user-1",
    email="owner@example.test",
    display_name="Owner",
    role="owner",
    workspace_id=WORKSPACE_ID,
    workspace_name="Workspace",
    is_platform_admin=False,
)


def _settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        reported_email_alias_secret=SECRET,
        reported_email_address="report@sicurre.com",
        reported_email_ingest_key="worker-secret",
        reported_email_max_message_bytes=1024 * 1024,
        reported_email_storage_backend="local",
        reported_email_local_dir=tmp_path,
    )


def _request(payload: bytes) -> Request:
    sent = False

    async def receive() -> dict:
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": payload, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/email/reports/token",
            "headers": [],
            "client": ("127.0.0.1", 4000),
        },
        receive,
    )


def test_alias_round_trip_and_address() -> None:
    codec = ReportAliasCodec(SECRET)
    token = codec.encode(WORKSPACE_ID)

    assert codec.decode(token) == WORKSPACE_ID
    assert report_address("report@sicurre.com", token) == f"report+{token}@sicurre.com"


def test_alias_rejects_tampering() -> None:
    codec = ReportAliasCodec(SECRET)
    token = codec.encode(WORKSPACE_ID)

    with pytest.raises(InvalidReportAlias):
        codec.decode(f"{token[:-1]}x")


def test_alias_requires_uuid_and_strong_secret() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        ReportAliasCodec("short")
    with pytest.raises(ValueError):
        ReportAliasCodec(SECRET).encode("workspace-1")


def test_sanitization_discards_outer_identity_and_redacts_original() -> None:
    raw = (
        b"From: Personal Owner <private@example.com>\r\n"
        b"To: report+token@sicurre.com\r\n"
        b"Subject: Fwd: Facture urgente\r\n"
        b"Content-Type: message/rfc822\r\n\r\n"
        b"From: Fraud <fraud@evil.test>\r\n"
        b"Subject: Facture urgente\r\n\r\n"
        b"Contactez victim@example.com ou +33 6 12 34 56 78."
    )

    evidence = json.loads(sanitized_evidence(raw))

    assert evidence["schema_version"] == "reported-email-v1"
    assert evidence["subject"] == "Facture urgente"
    assert "private@example.com" not in json.dumps(evidence)
    assert "fraud@evil.test" not in json.dumps(evidence)
    assert "victim@example.com" not in json.dumps(evidence)
    assert "[EMAIL]" in evidence["body"]
    assert "[PHONE]" in evidence["body"]


@pytest.mark.asyncio
async def test_local_store_is_workspace_scoped(tmp_path: Path) -> None:
    store = LocalReportedEmailStore(tmp_path)
    report_id = str(uuid.uuid4())

    result = await store.write(
        workspace_id=WORKSPACE_ID,
        report_id=report_id,
        payload=b'{"body":"evidence"}',
    )

    path = Path(result.storage_uri.removeprefix("file://"))
    assert path.parent.name == WORKSPACE_ID
    assert path.name == f"{report_id}.json"
    assert result.size_bytes == len(b'{"body":"evidence"}')


@pytest.mark.asyncio
async def test_report_address_is_workspace_scoped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(router, "get_settings", lambda: _settings(tmp_path))

    result = await router.get_report_address(USER)

    assert (
        ReportAliasCodec(SECRET).decode(result["address"].split("+", 1)[1].split("@", 1)[0])
        == WORKSPACE_ID
    )


@pytest.mark.asyncio
async def test_ingestion_rejects_wrong_worker_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(router, "get_settings", lambda: _settings(tmp_path))

    with pytest.raises(HTTPException) as exc_info:
        await router.ingest_reported_email(
            _request(b"Subject: Test\r\n\r\nBody"),
            ReportAliasCodec(SECRET).encode(WORKSPACE_ID),
            "wrong",
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_ingestion_persists_evidence_and_feedback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(router, "get_settings", lambda: _settings(tmp_path))
    queries: list[tuple[str, tuple]] = []

    async def query(sql: str, params: tuple = ()) -> list[dict]:
        queries.append((sql, params))
        if "FROM app_workspace_membership" in sql:
            return [{"auth_user_id": USER.id}]
        return []

    monkeypatch.setattr(router, "auth_query", query)
    token = ReportAliasCodec(SECRET).encode(WORKSPACE_ID)

    result = await router.ingest_reported_email(
        _request(b"Subject: Facture\r\n\r\nContact victim@example.com"),
        token,
        "worker-secret",
    )

    assert result == {"status": "accepted", "idempotent": False}
    assert any("INSERT INTO app_reported_email" in sql for sql, _ in queries)
    assert any("INSERT INTO app_feedback" in sql for sql, _ in queries)
