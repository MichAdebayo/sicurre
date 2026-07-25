"""Tests for workspace-scoped false-negative forwarding."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from data_platform.api.auth import AuthUser
from data_platform.api.routers import reported_email as router
from data_platform.services.reported_email import (
    InvalidReportAlias,
    LocalReportedEmailStore,
    R2ReportedEmailStore,
    ReportAliasCodec,
    _message_text,
    build_reported_email_store,
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
        reported_email_r2_bucket_name="reports",
        reported_email_r2_endpoint_url="https://account.r2.cloudflarestorage.com/reports",
        reported_email_r2_access_key_id="access",
        reported_email_r2_secret_access_key="secret",
        reported_email_r2_region="auto",
        reported_email_r2_prefix="reported-email",
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


def test_sanitization_reads_plain_multipart_parts() -> None:
    raw = (
        b"Subject: Multipart\r\n"
        b"Content-Type: multipart/mixed; boundary=x\r\n\r\n"
        b"--x\r\nContent-Type: text/plain\r\n\r\nVisible body\r\n"
        b"--x\r\nContent-Type: text/plain\r\nContent-Disposition: attachment\r\n\r\n"
        b"Hidden attachment\r\n--x--\r\n"
    )

    evidence = json.loads(sanitized_evidence(raw))

    assert "Visible body" in evidence["body"]
    assert "Hidden attachment" not in evidence["body"]


def test_message_text_falls_back_to_decoded_payload() -> None:
    message = MagicMock()
    message.is_multipart.return_value = False
    message.get_content.side_effect = LookupError
    message.get_payload.return_value = b"fallback"

    assert _message_text(message) == "fallback"


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
async def test_local_store_rejects_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes"):
        await LocalReportedEmailStore(tmp_path).write(
            workspace_id="../../outside",
            report_id="report",
            payload=b"evidence",
        )


@pytest.mark.asyncio
async def test_r2_store_configures_client_and_writes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = MagicMock()
    client_factory = MagicMock(return_value=client)
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=client_factory))
    store = R2ReportedEmailStore(_settings(tmp_path))

    result = await store.write(
        workspace_id=WORKSPACE_ID,
        report_id="report-id",
        payload=b"evidence",
    )

    assert result.storage_uri == (f"r2://reports/reported-email/{WORKSPACE_ID}/report-id.json")
    assert client_factory.call_args.kwargs["endpoint_url"] == (
        "https://account.r2.cloudflarestorage.com"
    )
    client.put_object.assert_called_once()


def test_r2_store_rejects_incomplete_config(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.reported_email_r2_secret_access_key = None

    with pytest.raises(RuntimeError, match="incomplete"):
        R2ReportedEmailStore(settings)


def test_store_factory_selects_backends_and_rejects_unknown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    assert isinstance(build_reported_email_store(settings), LocalReportedEmailStore)

    monkeypatch.setitem(
        sys.modules,
        "boto3",
        SimpleNamespace(client=MagicMock(return_value=MagicMock())),
    )
    settings.reported_email_storage_backend = "r2"
    assert isinstance(build_reported_email_store(settings), R2ReportedEmailStore)

    settings.reported_email_storage_backend = "unknown"
    with pytest.raises(RuntimeError, match="must be local or r2"):
        build_reported_email_store(settings)


def test_codec_configuration_errors(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.reported_email_alias_secret = None
    with pytest.raises(HTTPException) as missing:
        router._codec(settings)
    assert missing.value.status_code == 503

    settings.reported_email_alias_secret = "short"
    with pytest.raises(HTTPException) as weak:
        router._codec(settings)
    assert weak.value.status_code == 503


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
@pytest.mark.parametrize(
    ("token", "payload", "query_result", "expected_status"),
    [
        ("invalid", b"body", [{"auth_user_id": USER.id}], 404),
        ("valid", b"body", [], 404),
        ("valid", b"", [{"auth_user_id": USER.id}], 400),
        ("valid", b"x" * 20, [{"auth_user_id": USER.id}], 413),
    ],
)
async def test_ingestion_rejects_invalid_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    token: str,
    payload: bytes,
    query_result: list[dict],
    expected_status: int,
) -> None:
    settings = _settings(tmp_path)
    settings.reported_email_max_message_bytes = 10
    monkeypatch.setattr(router, "get_settings", lambda: settings)

    async def query(_sql: str, _params: tuple = ()) -> list[dict]:
        return query_result

    monkeypatch.setattr(router, "auth_query", query)
    resolved_token = ReportAliasCodec(SECRET).encode(WORKSPACE_ID) if token == "valid" else token

    with pytest.raises(HTTPException) as exc_info:
        await router.ingest_reported_email(
            _request(payload),
            resolved_token,
            "worker-secret",
        )

    assert exc_info.value.status_code == expected_status


@pytest.mark.asyncio
async def test_ingestion_returns_idempotent_for_existing_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(router, "get_settings", lambda: _settings(tmp_path))

    async def query(sql: str, _params: tuple = ()) -> list[dict]:
        if "FROM app_workspace_membership" in sql:
            return [{"auth_user_id": USER.id}]
        if "FROM app_reported_email" in sql:
            return [{"id": "existing"}]
        return []

    monkeypatch.setattr(router, "auth_query", query)
    result = await router.ingest_reported_email(
        _request(b"Subject: Existing\r\n\r\nBody"),
        ReportAliasCodec(SECRET).encode(WORKSPACE_ID),
        "worker-secret",
    )

    assert result == {"status": "accepted", "idempotent": True}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "idempotent"),
    [(Exception("UNIQUE constraint"), True), (RuntimeError("database down"), False)],
)
async def test_ingestion_handles_insert_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error: Exception,
    idempotent: bool,
) -> None:
    monkeypatch.setattr(router, "get_settings", lambda: _settings(tmp_path))

    async def query(sql: str, _params: tuple = ()) -> list[dict]:
        if "FROM app_workspace_membership" in sql:
            return [{"auth_user_id": USER.id}]
        if sql.strip().startswith("INSERT"):
            raise error
        return []

    monkeypatch.setattr(router, "auth_query", query)
    call = router.ingest_reported_email(
        _request(b"Subject: Failure\r\n\r\nBody"),
        ReportAliasCodec(SECRET).encode(WORKSPACE_ID),
        "worker-secret",
    )
    if idempotent:
        assert await call == {"status": "accepted", "idempotent": True}
    else:
        with pytest.raises(RuntimeError, match="database down"):
            await call


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
