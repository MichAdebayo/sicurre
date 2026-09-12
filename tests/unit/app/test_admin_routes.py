"""Unit contracts for the platform-admin overview, runtime health, and dataset routes."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from data_platform.api.auth import AuthUser
from data_platform.api.routers import admin
from data_platform.services import runtime_probes

ADMIN = AuthUser(
    id="admin-1",
    email="admin@example.test",
    display_name="Admin",
    role="owner",
    workspace_id="workspace-1",
    workspace_name="Workspace",
    is_platform_admin=True,
)


@pytest.mark.asyncio
async def test_admin_count_reads_the_first_row_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """The count helper unwraps the single aggregate row into an integer."""
    seen: list[tuple[str, tuple]] = []

    async def query(sql: str, params: tuple = ()) -> list[dict]:
        seen.append((sql, params))
        return [{"count": "7"}]

    monkeypatch.setattr(runtime_probes, "execute_runtime_query", query)
    assert await runtime_probes.quiet_count("SELECT COUNT(*) AS count FROM t", ("x",)) == 7
    assert seen == [("SELECT COUNT(*) AS count FROM t", ("x",))]


@pytest.mark.asyncio
async def test_admin_count_returns_zero_without_rows_or_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty result set and a failing query both degrade to zero."""

    async def no_rows(sql: str, params: tuple = ()) -> list[dict]:
        return []

    monkeypatch.setattr(runtime_probes, "execute_runtime_query", no_rows)
    assert await runtime_probes.quiet_count("SELECT COUNT(*) AS count FROM t") == 0

    async def failing(sql: str, params: tuple = ()) -> list[dict]:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(runtime_probes, "execute_runtime_query", failing)
    assert await runtime_probes.quiet_count("SELECT COUNT(*) AS count FROM t") == 0


@pytest.mark.asyncio
async def test_admin_rows_passes_rows_through_and_swallows_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The row helper returns the query rows verbatim, or an empty list on failure."""

    async def query(sql: str, params: tuple = ()) -> list[dict]:
        return [{"id": "a", "params": params}]

    monkeypatch.setattr(runtime_probes, "execute_runtime_query", query)
    assert await runtime_probes.quiet_rows("SELECT id FROM t", ("p",)) == [
        {"id": "a", "params": ("p",)}
    ]

    async def failing(sql: str, params: tuple = ()) -> list[dict]:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(runtime_probes, "execute_runtime_query", failing)
    assert await runtime_probes.quiet_rows("SELECT id FROM t") == []


@pytest.mark.asyncio
async def test_runtime_health_concatenates_every_probe_and_rolls_up_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The admin health report joins all probe families and reports the worst status."""
    inference = [{"component": "inference_health", "status": "ok"}]
    public_app = [{"component": "public_app_health", "status": "degraded"}]
    cloudflare = [{"component": "cloudflare_worker_binding", "status": "unknown"}]
    quarantine = {"component": "quarantine_storage", "status": "ok"}
    expected_scan_url = "https://app.example.test/v1/email/scan"
    calls: dict[str, object] = {}

    async def probe_inference(client: httpx.AsyncClient, url: str | None, key: str | None):
        assert isinstance(client, httpx.AsyncClient)
        calls["inference"] = (url, key)
        return inference

    async def probe_public_app(client: httpx.AsyncClient, url: str | None, internal: str | None):
        calls["public_app"] = (url, internal)
        return public_app, expected_scan_url

    async def probe_cloudflare(client: httpx.AsyncClient, *, expected_scan_url: str | None):
        calls["cloudflare"] = expected_scan_url
        return cloudflare

    monkeypatch.setattr(admin, "probe_inference_runtime", probe_inference)
    monkeypatch.setattr(admin, "probe_public_app_runtime", probe_public_app)
    monkeypatch.setattr(admin, "probe_cloudflare_runtime", probe_cloudflare)
    monkeypatch.setattr(admin, "quarantine_storage_status", lambda: quarantine)
    monkeypatch.setattr(
        admin,
        "get_settings",
        lambda: SimpleNamespace(
            inference_api_url="https://ml.example.test/v1/classify",
            inference_api_key="probe-key",
            public_api_url="https://app.example.test",
            internal_app_probe_url="http://app:8000",
        ),
    )

    result = await admin.get_admin_runtime_health(current_user=ADMIN)

    assert result["status"] == "degraded"
    assert result["public_api_host"] == "app.example.test"
    assert result["inference_api_url"] == "https://ml.example.test/v1/classify"
    assert result["expected_worker_scan_url"] == expected_scan_url
    assert result["components"] == inference + public_app + cloudflare + [quarantine]
    assert datetime.fromisoformat(result["checked_at"]).tzinfo is not None
    assert calls == {
        "inference": ("https://ml.example.test/v1/classify", "probe-key"),
        "public_app": ("https://app.example.test", "http://app:8000"),
        "cloudflare": expected_scan_url,
    }


@pytest.mark.asyncio
async def test_runtime_health_reports_no_host_without_a_public_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing public API URL yields a null host rather than an empty string."""

    async def probe_inference(*_: object, **__: object) -> list[dict]:
        return [{"component": "inference_api", "status": "down"}]

    async def probe_public_app(*_: object, **__: object) -> tuple[list[dict], str | None]:
        return [], None

    async def probe_cloudflare(*_: object, **__: object) -> list[dict]:
        return []

    monkeypatch.setattr(admin, "probe_inference_runtime", probe_inference)
    monkeypatch.setattr(admin, "probe_public_app_runtime", probe_public_app)
    monkeypatch.setattr(admin, "probe_cloudflare_runtime", probe_cloudflare)
    monkeypatch.setattr(
        admin,
        "quarantine_storage_status",
        lambda: {"component": "quarantine_storage", "status": "ok"},
    )
    monkeypatch.setattr(
        admin,
        "get_settings",
        lambda: SimpleNamespace(
            inference_api_url=None,
            inference_api_key=None,
            public_api_url=None,
            internal_app_probe_url=None,
        ),
    )

    result = await admin.get_admin_runtime_health(current_user=ADMIN)

    assert result["status"] == "down"
    assert result["public_api_host"] is None
    assert result["expected_worker_scan_url"] is None
    assert [item["component"] for item in result["components"]] == [
        "inference_api",
        "quarantine_storage",
    ]


@pytest.mark.asyncio
async def test_cloudflare_probe_reports_binding_and_rule_read_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transport errors on the Worker settings and routing rules become bounded failures."""

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

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/email/routing/addresses"):
            return httpx.Response(
                200,
                json={"result": [{"email": "owner@example.test", "verified": "2026-07-18"}]},
            )
        raise httpx.ConnectError("cloudflare offline", request=request)

    monkeypatch.setattr(runtime_probes, "quiet_rows", integration)
    monkeypatch.setattr(
        runtime_probes,
        "get_settings",
        lambda: SimpleNamespace(secret_encryption_key="key", environment="production"),
    )
    monkeypatch.setattr(runtime_probes, "decrypt_secret", lambda *_, **__: "token")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await runtime_probes.probe_cloudflare_runtime(
            client, expected_scan_url="https://app.example.test/v1/email/scan"
        )

    by_component = {item["component"]: item for item in result}
    binding = by_component["cloudflare_worker_binding"]
    assert binding["status"] == "down"
    assert binding["message"] == "Could not read Cloudflare Worker bindings."
    assert binding["detail"] == "cloudflare offline"
    assert binding["checked_url"].endswith(
        "/accounts/account/workers/scripts/sicurre-mail/settings"
    )

    rule = by_component["cloudflare_routing_rule"]
    assert rule["status"] == "degraded"
    assert rule["message"] == "Could not verify Cloudflare routing rule."
    assert rule["detail"] == "cloudflare offline"
    assert rule["checked_url"].endswith("/zones/zone/email/routing/rules")

    assert by_component["cloudflare_email_sending"]["status"] == "ok"


@pytest.mark.asyncio
async def test_admin_overview_assembles_counts_and_recent_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The overview maps each count query to its summary key and each list to its section."""
    counts = {
        "FROM app_workspace_membership": 12,
        "FROM app_workspace": 3,
        "FROM app_inference_event": 250,
        "feedback_type = 'false_negative'": 2,
        "FROM app_feedback": 9,
        "FROM app_reported_email": 4,
        "FROM app_quarantine_item": 5,
        "cloudflare_integration WHERE status = 'active'": 1,
        "FROM cloudflare_integration": 2,
        "FROM app_support_request": 6,
    }

    async def fake_count(sql: str, params: tuple = ()) -> int:
        for fragment, value in counts.items():
            if fragment in sql:
                return value
        raise AssertionError(f"unexpected count query: {sql}")

    verdicts = [{"verdict": "phishing", "count": 40}, {"verdict": "legitimate", "count": 210}]
    feedback_by_type = [{"feedback_type": "false_negative", "count": 2}]
    domains = [{"zone_name": "example.test", "status": "active"}]
    recent_feedback = [{"id": "fb-1", "feedback_type": "false_negative"}]
    recent_quarantine = [{"id": "q-1", "status": "held"}]
    recent_support = [{"id": "s-1", "status": "open"}]

    async def fake_rows(sql: str, params: tuple = ()) -> list[dict]:
        if "GROUP BY 1" in sql:
            return verdicts
        if "GROUP BY feedback_type" in sql:
            return feedback_by_type
        if "SELECT zone_name, status, user_email" in sql:
            return domains
        if "LEFT JOIN app_workspace_membership" in sql:
            return recent_feedback
        if "FROM app_quarantine_item" in sql:
            return recent_quarantine
        if "FROM app_support_request" in sql:
            return recent_support
        raise AssertionError(f"unexpected row query: {sql}")

    monkeypatch.setattr(admin, "quiet_count", fake_count)
    monkeypatch.setattr(admin, "quiet_rows", fake_rows)

    result = await admin.get_admin_overview(current_user=ADMIN)

    assert result["summary"] == {
        "workspaces_count": 3,
        "members_count": 12,
        "threat_events_count": 250,
        "feedback_count": 9,
        "false_negative_count": 2,
        "reported_email_count": 4,
        "quarantine_held_count": 5,
        "cloudflare_integrations_count": 2,
        "cloudflare_active_count": 1,
        "support_open_count": 6,
    }
    assert result["verdicts"] == verdicts
    assert result["feedback_by_type"] == feedback_by_type
    assert result["cloudflare_domains"] == domains
    assert result["recent_feedback"] == recent_feedback
    assert result["recent_quarantine"] == recent_quarantine
    assert result["recent_support"] == recent_support


@pytest.mark.asyncio
async def test_list_datasets_alias_serialises_rows_with_and_without_publication() -> None:
    """Dataset rows are serialised with a UTC suffix on published_at, or null when unpublished."""
    published = datetime(2026, 7, 18, 9, 30, tzinfo=UTC).replace(tzinfo=None)
    rows = [
        SimpleNamespace(
            id=1, version_tag="v2", item_count=120, status="published", published_at=published
        ),
        SimpleNamespace(id=2, version_tag="v1", item_count=80, status="draft", published_at=None),
    ]
    result = MagicMock()
    result.all.return_value = rows
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    payload = await admin.list_datasets_alias(session=session, current_user=ADMIN)

    assert payload == [
        {
            "id": "1",
            "version_tag": "v2",
            "item_count": 120,
            "status": "published",
            "published_at": "2026-07-18T09:30:00Z",
        },
        {
            "id": "2",
            "version_tag": "v1",
            "item_count": 80,
            "status": "draft",
            "published_at": None,
        },
    ]
    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    assert "FROM data_dataset ORDER BY version_tag DESC" in str(statement)


@pytest.mark.asyncio
async def test_list_datasets_alias_returns_empty_list_when_the_query_fails() -> None:
    """A failing dataset query degrades to an empty list instead of a server error."""
    session = MagicMock()
    session.execute = AsyncMock(side_effect=RuntimeError("relation does not exist"))

    assert await admin.list_datasets_alias(session=session, current_user=ADMIN) == []


def test_execute_pipeline_runs_the_scheduler_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """The background pipeline invokes the make target and checks its exit status."""
    run = MagicMock()
    monkeypatch.setattr(admin.subprocess, "run", run)

    admin.execute_pipeline()

    run.assert_called_once_with(["make", "run-scheduler"], check=True)


def test_execute_pipeline_logs_failures_without_raising(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A failing scheduler run is logged with its traceback and never propagates."""

    def failing(*_: object, **__: object) -> None:
        raise RuntimeError("make exited with status 2")

    monkeypatch.setattr(admin.subprocess, "run", failing)

    with caplog.at_level("ERROR", logger=admin.logger.name):
        admin.execute_pipeline()

    record = next(
        item for item in caplog.records if "Scheduled pipeline execution failed" in item.message
    )
    assert record.exc_info is not None
    assert "make exited with status 2" in str(record.exc_info[1])
