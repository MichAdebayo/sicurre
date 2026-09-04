"""Unit contracts for the platform-admin runtime health diagnostics."""

from __future__ import annotations

import json

from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from data_platform.api.auth import AuthUser
from data_platform.api.routers import app_routes

USER = AuthUser(
    id="user-1",
    email="owner@example.test",
    display_name="Owner",
    role="owner",
    workspace_id="workspace-1",
    workspace_name="Example",
    is_platform_admin=False,
)


def test_component_rollup_uses_worst_status() -> None:
    """The aggregate status preserves the most urgent component condition."""
    assert app_routes._component_rollup([{"status": "ok"}]) == "ok"
    assert app_routes._component_rollup([{"status": "unknown"}]) == "unknown"
    assert app_routes._component_rollup([{"status": "degraded"}]) == "degraded"
    assert app_routes._component_rollup([{"status": "degraded"}, {"status": "down"}]) == "down"


@pytest.mark.asyncio
async def test_inference_probe_requires_configured_url() -> None:
    """An absent classifier URL is reported as a down dependency."""
    async with httpx.AsyncClient() as client:
        result = await app_routes._probe_inference_runtime(client, None)

    assert result == [
        {
            "component": "inference_api",
            "status": "down",
            "message": "SICURRE_INFERENCE_API_URL is not configured.",
            "detail": None,
            "checked_url": None,
            "latency_ms": None,
        }
    ]


@pytest.mark.asyncio
async def test_inference_probe_reports_health_and_readiness() -> None:
    """Health and readiness remain separate, actionable classifier checks."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"verdict": "legitimate"})
        status = 200 if request.url.path == "/v1/health" else 503
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await app_routes._probe_inference_runtime(
            client, "https://ml.example/v1/classify", "probe-key"
        )

    assert [(item["component"], item["status"]) for item in result] == [
        ("inference_health", "ok"),
        ("inference_ready", "degraded"),
        ("inference_contract", "ok"),
    ]


@pytest.mark.asyncio
async def test_inference_probe_reports_network_failure() -> None:
    """Network exceptions produce bounded down statuses for each probe."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await app_routes._probe_inference_runtime(
            client, "https://ml.example/v1/classify", "probe-key"
        )

    assert [item["status"] for item in result] == ["down", "down", "down"]
    assert all(item["detail"] == "offline" for item in result)


@pytest.mark.asyncio
async def test_public_app_probe_proves_gateway_auth_boundary() -> None:
    """The preflight expects health success and an unauthenticated scan rejection."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200 if request.method == "GET" else 401)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result, scan_url = await app_routes._probe_public_app_runtime(client, "https://app.example")

    assert scan_url == "https://app.example/v1/email/scan"
    assert [(item["component"], item["status"]) for item in result] == [
        ("public_app_health", "ok"),
        ("email_scan_gateway", "ok"),
    ]


@pytest.mark.asyncio
async def test_public_app_probe_uses_private_route_without_changing_worker_url() -> None:
    """Probe privately while preserving the public URL expected by Cloudflare."""
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200 if request.method == "GET" else 401)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result, scan_url = await app_routes._probe_public_app_runtime(
            client,
            "https://sicurre.example",
            "http://sicurre-app:5173",
        )

    assert scan_url == "https://sicurre.example/v1/email/scan"
    assert requested_urls == [
        "http://sicurre-app:5173/health",
        "http://sicurre-app:5173/v1/email/scan",
    ]
    assert [item["status"] for item in result] == ["ok", "ok"]


@pytest.mark.asyncio
async def test_public_app_probe_rejects_missing_and_unreachable_runtime() -> None:
    """Missing configuration and connection failures cannot appear healthy."""
    async with httpx.AsyncClient() as client:
        missing, scan_url = await app_routes._probe_public_app_runtime(client, None)
    assert missing[0]["status"] == "down"
    assert scan_url is None

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        unreachable, _ = await app_routes._probe_public_app_runtime(client, "https://app.example")
    assert [item["status"] for item in unreachable] == ["down", "down"]


@pytest.mark.asyncio
async def test_cloudflare_probe_handles_absent_and_incomplete_integration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No integration is unknown, while incomplete persisted state is down."""

    async def no_rows(*_: object, **__: object) -> list[dict]:
        return []

    monkeypatch.setattr(app_routes, "_admin_rows", no_rows)
    async with httpx.AsyncClient() as client:
        absent = await app_routes._probe_cloudflare_runtime(
            client, expected_scan_url="https://app.example/v1/email/scan"
        )
    assert absent[0]["status"] == "unknown"

    async def incomplete(*_: object, **__: object) -> list[dict]:
        return [{"zone_name": "example.test", "status": "active"}]

    monkeypatch.setattr(app_routes, "_admin_rows", incomplete)
    async with httpx.AsyncClient() as client:
        result = await app_routes._probe_cloudflare_runtime(
            client, expected_scan_url="https://app.example/v1/email/scan"
        )
    assert result[0]["status"] == "down"
    assert "missing token" in result[0]["message"]


@pytest.mark.asyncio
async def test_cloudflare_probe_validates_all_runtime_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker binding, routing rule, and Email Sending are independently proven."""

    async def integration(*_: object, **__: object) -> list[dict]:
        return [
            {
                "zone_name": "example.test",
                "destination_email": "owner@example.test",
                "zone_id": "zone",
                "account_id": "account",
                "worker_name": "sicurre-mail",
                "rule_id": "rule",
                "api_token": "encrypted",
                "status": "active",
            }
        ]

    expected_scan_url = "https://app.example/v1/email/scan"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer token"
        if request.url.path.endswith("/settings"):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "bindings": [{"name": "SICURRE_SCAN_URL", "text": expected_scan_url}]
                    }
                },
            )
        if request.url.path.endswith("/email/routing/rules"):
            return httpx.Response(200, json={"result": [{"id": "rule", "enabled": True}]})
        return httpx.Response(
            200,
            json={"result": [{"email": "owner@example.test", "verified": "2026-07-18"}]},
        )

    monkeypatch.setattr(app_routes, "_admin_rows", integration)
    monkeypatch.setattr(
        app_routes,
        "get_settings",
        lambda: SimpleNamespace(secret_encryption_key="key", environment="production"),
    )
    monkeypatch.setattr(app_routes, "decrypt_secret", lambda *_, **__: "token")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await app_routes._probe_cloudflare_runtime(
            client, expected_scan_url=expected_scan_url
        )

    assert [(item["component"], item["status"]) for item in result] == [
        ("cloudflare_worker_binding", "ok"),
        ("cloudflare_routing_rule", "ok"),
        ("cloudflare_email_sending", "ok"),
    ]


def test_dmarc_report_rejects_another_domain() -> None:
    """A report cannot be imported into a different connected domain."""
    payload = b"""<feedback>
      <policy_published><domain>foreign.test</domain></policy_published>
    </feedback>"""

    with pytest.raises(HTTPException) as exc_info:
        app_routes._parse_dmarc_report(payload, "example.test")

    assert exc_info.value.status_code == 400
    assert "does not match" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_kpis_aggregate_each_class_for_current_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """KPI totals preserve all three model classes and quarantine aliases."""
    captured_sql = ""

    async def threat_count(_: str, _domain: str | None = None) -> int:
        return 10

    async def query(sql: str, *_: object, **__: object) -> list[dict]:
        nonlocal captured_sql
        captured_sql = sql
        if "COUNT(*) AS total" in sql:
            return [{"total": 2}]
        return [
            {"label_verdict": "phishing", "cnt": 2},
            {"label_verdict": "quarantine", "cnt": 1},
            {"label_verdict": "spam", "cnt": 3},
            {"label_verdict": "legitimate", "cnt": 4},
        ]

    monkeypatch.setattr(app_routes, "_workspace_threat_count", threat_count)
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    async def allow_domain(_domain: str, _workspace_id: str) -> None:
        return None

    monkeypatch.setattr(app_routes, "_require_workspace_domain", allow_domain)
    result = await app_routes.get_kpis("example.test", object(), USER)  # type: ignore[arg-type]

    assert result["raw_records_count"] == 10
    assert result["threats_phishing_count"] == 3
    assert result["threats_spam_count"] == 3
    assert result["threats_legitimate_count"] == 4
    assert "label_verdict" in captured_sql


@pytest.mark.asyncio
async def test_threat_list_masks_non_threat_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legitimate content is masked while quarantined evidence stays reviewable."""

    captured_sql = ""

    async def query(sql: str, *_: object, **__: object) -> list[dict]:
        nonlocal captured_sql
        captured_sql = sql
        if "COUNT(*) AS total" in sql:
            return [{"total": 2}]
        base = {
            "message_id": "message",
            "confidence": 0.9,
            "received_at": "2026-07-17T00:00:00Z",
            "latency_ms": 20,
            "explanation": None,
        }
        return [
            {
                **base,
                "id": "safe",
                "subject": "Private subject",
                "sender": "person@example.test",
                "body_preview": "Private body",
                "verdict": "legitimate",
                "status": "unexpected",
            },
            {
                **base,
                "id": "held",
                "subject": "Suspicious invoice",
                "sender": "attacker@example.test",
                "body_preview": "Open attachment",
                "verdict": "quarantine",
                "status": "active",
            },
        ]

    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    async def allow_domain(_domain: str, _workspace_id: str) -> None:
        return None

    monkeypatch.setattr(app_routes, "_require_workspace_domain", allow_domain)

    result = await app_routes.get_threats("example.test", USER)

    assert result["items"][0]["subject"] == "[Masqué par Sicurre]"
    assert result["items"][0]["status"] == "active"
    assert result["items"][1]["subject"] == "Suspicious invoice"
    assert result["items"][1]["sender"] == "attacker@example.test"
    assert "label_verdict" in captured_sql


@pytest.mark.asyncio
async def test_cloudflare_probe_reports_undecryptable_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale encryption key is reported without exposing the token."""

    async def integration(*_: object, **__: object) -> list[dict]:
        return [
            {
                "zone_name": "example.test",
                "zone_id": "zone",
                "account_id": "account",
                "worker_name": "worker",
                "rule_id": None,
                "api_token": "encrypted",
                "status": "active",
            }
        ]

    monkeypatch.setattr(app_routes, "_admin_rows", integration)
    monkeypatch.setattr(
        app_routes,
        "get_settings",
        lambda: SimpleNamespace(secret_encryption_key="key", environment="production"),
    )
    monkeypatch.setattr(
        app_routes,
        "decrypt_secret",
        lambda *_, **__: (_ for _ in ()).throw(ValueError("bad key")),
    )
    async with httpx.AsyncClient() as client:
        result = await app_routes._probe_cloudflare_runtime(
            client, expected_scan_url="https://app.example/v1/email/scan"
        )

    assert result[0]["status"] == "down"
    assert result[0]["detail"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "payload", "expected_status", "message_fragment"),
    [
        (403, {"success": False}, "down", "Routing destinations"),
        (500, {"success": False}, "degraded", "could not be verified"),
        (200, {"result": []}, "degraded", "not verified"),
    ],
)
async def test_cloudflare_probe_distinguishes_email_sending_failures(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    payload: dict,
    expected_status: str,
    message_fragment: str,
) -> None:
    """Admin health gives operators the actual Email Sending remediation."""

    async def integration(*_: object, **__: object) -> list[dict]:
        return [
            {
                "zone_name": "example.test",
                "destination_email": "owner@example.test",
                "zone_id": "zone",
                "account_id": "account",
                "worker_name": "worker",
                "rule_id": None,
                "api_token": "encrypted",
                "status": "active",
            }
        ]

    expected_scan_url = "https://app.example/v1/email/scan"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/settings"):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "bindings": [{"name": "SICURRE_SCAN_URL", "text": expected_scan_url}]
                    }
                },
            )
        return httpx.Response(status_code, json=payload)

    monkeypatch.setattr(app_routes, "_admin_rows", integration)
    monkeypatch.setattr(
        app_routes,
        "get_settings",
        lambda: SimpleNamespace(secret_encryption_key="key", environment="production"),
    )
    monkeypatch.setattr(app_routes, "decrypt_secret", lambda *_, **__: "token")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await app_routes._probe_cloudflare_runtime(
            client, expected_scan_url=expected_scan_url
        )

    sending = next(item for item in result if item["component"] == "cloudflare_email_sending")
    assert sending["status"] == expected_status
    assert message_fragment in sending["message"]


@pytest.mark.asyncio
async def test_cloudflare_probe_handles_email_sending_probe_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed readiness request degrades only the Email Sending component."""

    async def integration(*_: object, **__: object) -> list[dict]:
        return [
            {
                "zone_name": "example.test",
                "destination_email": "owner@example.test",
                "zone_id": "zone",
                "account_id": "account",
                "worker_name": "worker",
                "rule_id": None,
                "api_token": "encrypted",
                "status": "active",
            }
        ]

    expected_scan_url = "https://app.example/v1/email/scan"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/settings"):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "bindings": [{"name": "SICURRE_SCAN_URL", "text": expected_scan_url}]
                    }
                },
            )
        raise httpx.ConnectError("sending API offline", request=request)

    monkeypatch.setattr(app_routes, "_admin_rows", integration)
    monkeypatch.setattr(
        app_routes,
        "get_settings",
        lambda: SimpleNamespace(secret_encryption_key="key", environment="production"),
    )
    monkeypatch.setattr(app_routes, "decrypt_secret", lambda *_, **__: "token")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await app_routes._probe_cloudflare_runtime(
            client, expected_scan_url=expected_scan_url
        )

    sending = next(item for item in result if item["component"] == "cloudflare_email_sending")
    assert sending["status"] == "degraded"
    assert sending["detail"] == "sending API offline"


@pytest.mark.parametrize(
    ("environment", "backend", "factory_error", "expected"),
    [
        ("development", "local", None, "ok"),
        ("production", "local", None, "down"),
        ("production", "r2", RuntimeError("missing bucket"), "down"),
        ("production", "r2", None, "ok"),
    ],
)
def test_quarantine_storage_runtime_status(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    backend: str,
    factory_error: RuntimeError | None,
    expected: str,
) -> None:
    """Admin health reflects environment-safe quarantine custody."""
    settings = SimpleNamespace(
        environment=environment,
        quarantine_storage_backend=backend,
        quarantine_r2_bucket_name="private-quarantine",
    )
    monkeypatch.setattr(app_routes, "get_settings", lambda: settings)

    def build(_: object) -> object:
        if factory_error:
            raise factory_error
        return object()

    monkeypatch.setattr(app_routes, "build_quarantine_store", build)

    assert app_routes._quarantine_storage_status()["status"] == expected


@pytest.mark.asyncio
async def test_contract_probe_catches_the_incident_06_condition() -> None:
    """Health and readiness green, classification refused — the actual outage."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(401)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await app_routes._probe_inference_runtime(
            client, "https://ml.example/v1/classify", "wrong-key"
        )

    statuses = {item["component"]: item["status"] for item in result}
    assert statuses["inference_health"] == "ok"
    assert statuses["inference_ready"] == "ok"
    assert statuses["inference_contract"] == "down"
    assert app_routes._component_rollup(result) == "down"


@pytest.mark.asyncio
async def test_contract_probe_reports_a_missing_key_without_calling_out() -> None:
    """An unset key is the incident's root cause and needs no network call."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await app_routes._probe_inference_contract(
            client, "https://ml.example/v1/classify", None
        )

    assert result["status"] == "down"
    assert "SICURRE_INFERENCE_API_KEY" in result["message"]
    assert calls == []


@pytest.mark.asyncio
async def test_contract_probe_rejects_a_verdictless_success() -> None:
    """HTTP 200 without a verdict is not a working classifier."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"detail": "accepted"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await app_routes._probe_inference_contract(
            client, "https://ml.example/v1/classify", "probe-key"
        )

    assert result["status"] == "degraded"


@pytest.mark.asyncio
async def test_contract_probe_never_sends_client_content_or_leaks_the_key() -> None:
    """The probe payload is synthetic and the key stays out of the report."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"verdict": "legitimate"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await app_routes._probe_inference_contract(
            client, "https://ml.example/v1/classify", "super-secret-key"
        )

    body = json.loads(seen["body"])
    assert seen["auth"] == "Bearer super-secret-key"
    assert body["sender"].endswith("@sicurre.invalid")
    assert body["use_llm"] is False and body["use_virustotal"] is False
    assert "super-secret-key" not in str(result)


@pytest.mark.asyncio
async def test_contract_probe_degrades_on_an_unexpected_status() -> None:
    """A 500 is not a credential problem, so it is not reported as one."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await app_routes._probe_inference_contract(
            client, "https://ml.example/v1/classify", "probe-key"
        )

    assert result["status"] == "degraded"
    assert "500" in result["message"]


@pytest.mark.asyncio
async def test_contract_probe_survives_a_non_json_success() -> None:
    """A 200 whose body will not parse must not raise inside the health page."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>not json</html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await app_routes._probe_inference_contract(
            client, "https://ml.example/v1/classify", "probe-key"
        )

    assert result["status"] == "degraded"
    assert "verdict" in result["message"]
