"""Drive ``POST /v1/integrations/cloudflare/setup`` through every branch.

The route is called directly with patched seams: the database, the settings,
the token cipher, the Cloudflare provisioner and the certificate probe. The
background coroutine it schedules is run in the test so its writes can be read.
"""

from __future__ import annotations

import hashlib
import logging
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import BackgroundTasks, HTTPException
from starlette.requests import Request

from data_platform.api.auth import AuthUser
from data_platform.api.routers import integrations
from data_platform.api.routers.integrations import CloudflareSetupRequest, setup_cloudflare
from data_platform.services import cloudflare_onboarding, domain_shield_sync
from data_platform.services.cloudflare_provisioner import ProvisioningResult

# slowapi keeps one in-memory counter per client address for the whole test
# process and the route allows ten calls an hour. This module drives the route
# far more often than that, so it calls the undecorated coroutine.
_setup = setup_cloudflare.__wrapped__

ZONE = "example.test"
SPF_EXISTING = "v=spf1 include:_spf.google.com ~all"
SPF_MERGED = "v=spf1 include:_spf.google.com include:_spf.mx.cloudflare.net ~all"
SPF_FROM_NOTHING = "v=spf1 include:_spf.mx.cloudflare.net ~all"
DKIM_EXISTING = "v=DKIM1; k=rsa; p=" + "A" * 120
DMARC_OWN_REJECT = "v=DMARC1; p=reject; rua=mailto:owner@example.test"
DMARC_OWN_REJECT_MERGED = (
    "v=DMARC1; p=reject; rua=mailto:owner@example.test,mailto:dmarc@sicurre.com"
)
DMARC_SICURRE_QUARANTINE = "v=DMARC1; p=quarantine; rua=mailto:dmarc@sicurre.com"
DMARC_SICURRE_REJECT = "v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com"


# --------------------------------------------------------------------------- Helpers


def _user() -> AuthUser:
    return AuthUser(
        id="user-1",
        email="owner@example.test",
        display_name="Owner",
        role="owner",
        workspace_id="workspace-1",
        workspace_name="Workspace",
        is_platform_admin=False,
    )


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/integrations/cloudflare/setup",
            "headers": [],
            "client": ("127.0.0.1", 4000),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


def _settings(public_api_url: str | None = "https://api.sicurre.test/") -> SimpleNamespace:
    return SimpleNamespace(
        public_api_url=public_api_url,
        secret_encryption_key=None,
        environment="test",
    )


def _payload(**overrides: Any) -> CloudflareSetupRequest:
    fields: dict[str, Any] = {
        "cf_api_token": "payload-token",
        "zone_name": ZONE,
        "destination_email": "inbox@example.test",
    }
    fields.update(overrides)
    return CloudflareSetupRequest(**fields)


def _txt(name: str, content: str) -> dict[str, str]:
    return {"type": "TXT", "name": name, "content": content}


def _result(*, destination_verified: bool) -> ProvisioningResult:
    return ProvisioningResult(
        zone_id="zone-1",
        zone_name=ZONE,
        account_id="account-1",
        worker_name="sicurre-example",
        rule_id="rule-1",
        destination_email="inbox@example.test",
        shared_secret_hash="hash-1",
        shared_secret_plain="plain-1",
        destination_verified=destination_verified,
    )


def _column_names(sql: str) -> list[str]:
    """The column list of the shield INSERT, in the order the values bind to it."""
    inner = sql.split("app_domain_shield_status (", 1)[1].split(")", 1)[0]
    return [name.strip() for name in inner.replace("\n", " ").split(",")]


class _Queries:
    """Answer SQL by fragment and record every statement in order."""

    def __init__(self, answers: dict[str, list[dict[str, Any]] | Exception] | None = None):
        self.answers = dict(answers or {})
        self.statements: list[tuple[str, tuple[Any, ...]]] = []

    async def __call__(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        self.statements.append((sql, params))
        for fragment, answer in self.answers.items():
            if fragment in sql:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        return []

    def matching(self, fragment: str) -> list[tuple[str, tuple[Any, ...]]]:
        return [(sql, params) for sql, params in self.statements if fragment in sql]

    def one(self, fragment: str) -> tuple[str, tuple[Any, ...]]:
        found = self.matching(fragment)
        assert len(found) == 1, f"{len(found)} statements match {fragment!r}"
        return found[0]


def _provisioner(
    *,
    records: list[dict[str, str]] | None = None,
    records_error: Exception | None = None,
    result: ProvisioningResult | Exception | None = None,
    worker_error: Exception | None = None,
) -> tuple[type, SimpleNamespace]:
    """A provisioner class whose instances share one log of what they were asked."""
    log = SimpleNamespace(tokens=[], deployed=[], workers=[], provisions=[])

    class Stub:
        def __init__(self, api_token: str) -> None:
            log.tokens.append(api_token)

        async def get_zone(self, _zone_name: str) -> tuple[str, str]:
            return "zone-1", "active"

        async def get_dns_records(self, _zone_id: str) -> list[dict[str, str]]:
            if records_error is not None:
                raise records_error
            return list(records or [])

        async def deploy_dns_record(self, **kwargs: Any) -> None:
            log.deployed.append(kwargs)

        async def deploy_email_worker(self, **kwargs: Any) -> None:
            if worker_error is not None:
                raise worker_error
            log.workers.append(kwargs)

        async def provision(self, **kwargs: Any) -> ProvisioningResult:
            log.provisions.append(kwargs)
            if isinstance(result, Exception):
                raise result
            assert result is not None, "provision() called without a configured result"
            return result

    return Stub, log


async def _sync_ok(**_kwargs: Any) -> dict[str, Any]:
    return {"zone_id": "zone-1", "reputation_score": 100, "score_grade": "A"}


async def _sync_failing(**_kwargs: Any) -> dict[str, Any]:
    raise integrations.CloudflareAPIError("DNS: Edit permission is missing")


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    queries: _Queries,
    provisioner: type,
    *,
    settings: SimpleNamespace | None = None,
    sync: Any = _sync_ok,
) -> None:
    monkeypatch.setattr(integrations, "_ensure_tables", lambda: None)
    monkeypatch.setattr(integrations, "_async_query", queries)
    monkeypatch.setattr(integrations, "get_settings", lambda: settings or _settings())
    monkeypatch.setattr(integrations, "decrypt_secret", lambda *_a, **_k: "stored-token")
    monkeypatch.setattr(integrations, "encrypt_provider_token", lambda token: f"enc:{token}")
    monkeypatch.setattr(integrations, "CloudflareProvisioner", provisioner)
    monkeypatch.setattr(integrations, "sync_domain_shield_dns", sync)
    # The background task and the DNS sync live in their own services.
    monkeypatch.setattr(cloudflare_onboarding, "CloudflareProvisioner", provisioner)
    monkeypatch.setattr(cloudflare_onboarding, "execute_runtime_query", queries)
    monkeypatch.setattr(domain_shield_sync, "execute_runtime_query", queries)
    monkeypatch.setattr(domain_shield_sync, "get_ssl_expiry_days", lambda _domain: 30)


def _connected_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": "integration-1",
        "status": "active",
        "zone_id": "zone-1",
        "account_id": "account-1",
        "worker_name": "sicurre-example",
        "destination_email": "inbox@example.test",
    }
    row.update(overrides)
    return row


def _assert_resync_writes(queries: _Queries) -> None:
    """The three writes every successful re-sync ends with."""
    _, token_params = queries.one("SET api_token=?, error_message=NULL")
    assert token_params[0] == "enc:payload-token"
    assert token_params[2] == "integration-1"

    _, config_params = queries.one("INSERT INTO app_cloudflare_config")
    assert config_params[0] == "workspace-1"
    assert config_params[1] == "enc:payload-token"
    assert config_params[2] == config_params[3] == token_params[1]

    _, alert_params = queries.one("INSERT INTO app_alert_history")
    assert alert_params[1:5] == (
        "workspace-1",
        ZONE,
        "Configuration DNS appliquée",
        f"{ZONE} est synchronisé avec Cloudflare.",
    )


# --------------------------------------------------------------------------- Token lookup


@pytest.mark.asyncio
async def test_a_missing_payload_token_falls_back_to_the_stored_workspace_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a token in the body, the saved workspace token is decrypted and used."""
    queries = _Queries({"SELECT api_token FROM app_cloudflare_config": [{"api_token": "enc:x"}]})
    provisioner, log = _provisioner()
    _patch(monkeypatch, queries, provisioner)
    decrypt_calls: list[tuple[Any, ...]] = []

    def decrypt(token: str, **kwargs: Any) -> str:
        decrypt_calls.append((token, kwargs))
        return "stored-token"

    monkeypatch.setattr(integrations, "decrypt_secret", decrypt)

    response = await _setup(_payload(cf_api_token=None), BackgroundTasks(), _request(), _user())

    assert response["status"] == "provisioning"
    assert decrypt_calls == [("enc:x", {"configured_key": None, "environment": "test"})]
    assert log.tokens == ["stored-token"]
    _, insert_params = queries.one("INSERT INTO cloudflare_integration")
    assert insert_params[10] == "enc:stored-token"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "token_rows",
    [[], [{"api_token": None}], [{"api_token": ""}]],
    ids=["no-config-row", "null-token", "empty-token"],
)
async def test_no_token_anywhere_is_a_bad_request(
    monkeypatch: pytest.MonkeyPatch, token_rows: list[dict[str, Any]]
) -> None:
    """No body token and no usable stored token means nothing can be provisioned."""
    queries = _Queries({"SELECT api_token FROM app_cloudflare_config": token_rows})
    provisioner, log = _provisioner()
    _patch(monkeypatch, queries, provisioner)

    with pytest.raises(HTTPException) as exc_info:
        await _setup(_payload(cf_api_token=None), BackgroundTasks(), _request(), _user())

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Cloudflare API token is not configured"
    assert log.tokens == []
    assert queries.matching("INSERT INTO") == []


# --------------------------------------------------------------------------- Existing rows


@pytest.mark.asyncio
async def test_a_failed_attempt_with_remote_resources_is_kept_and_resynced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An error row that already owns a zone, account and worker is not discarded."""
    row = _connected_row(status="error")
    queries = _Queries({"SELECT * FROM cloudflare_integration": [row]})
    provisioner, log = _provisioner()
    _patch(monkeypatch, queries, provisioner)

    response = await _setup(_payload(), BackgroundTasks(), _request(), _user())

    assert response["integration_id"] == "integration-1"
    assert response["status"] == "error"
    assert queries.matching("DELETE FROM cloudflare_integration") == []
    assert queries.matching("INSERT INTO cloudflare_integration") == []
    assert len(log.workers) == 1


@pytest.mark.asyncio
async def test_a_domain_still_provisioning_is_reported_as_a_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second setup while the background task runs is refused, not restarted."""
    row = _connected_row(status="provisioning")
    queries = _Queries({"SELECT * FROM cloudflare_integration": [row]})
    provisioner, log = _provisioner()
    _patch(monkeypatch, queries, provisioner)

    with pytest.raises(HTTPException) as exc_info:
        await _setup(_payload(), BackgroundTasks(), _request(), _user())

    assert exc_info.value.status_code == 409
    assert ZONE in exc_info.value.detail
    assert "already running" in exc_info.value.detail
    assert log.tokens == []
    assert queries.matching("UPDATE") == []


@pytest.mark.asyncio
async def test_a_failed_dns_sync_on_a_connected_domain_records_the_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The DNS failure is written on the row with the token, then surfaced as 502."""
    queries = _Queries({"SELECT * FROM cloudflare_integration": [_connected_row()]})
    provisioner, log = _provisioner()
    _patch(monkeypatch, queries, provisioner, sync=_sync_failing)

    with pytest.raises(HTTPException) as exc_info:
        await _setup(_payload(), BackgroundTasks(), _request(), _user())

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == (
        "Cloudflare DNS update failed: DNS: Edit permission is missing"
    )
    assert log.tokens == ["payload-token"]
    assert log.workers == []
    _, params = queries.one("UPDATE cloudflare_integration SET error_message=?")
    assert params[0] == "DNS: Edit permission is missing"
    assert params[1] == "enc:payload-token"
    assert params[3] == "integration-1"
    assert queries.matching("INSERT INTO app_alert_history") == []


@pytest.mark.asyncio
async def test_a_connected_gateway_gets_its_worker_redeployed_with_the_scan_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row with a gateway redeploys the Worker and rotates the shared secret."""
    queries = _Queries({"SELECT * FROM cloudflare_integration": [_connected_row()]})
    provisioner, log = _provisioner()
    _patch(monkeypatch, queries, provisioner)

    response = await _setup(
        _payload(fix_spf=True, fix_dmarc=True), BackgroundTasks(), _request(), _user()
    )

    assert log.tokens == ["payload-token"]
    assert len(log.workers) == 1
    worker = log.workers[0]
    assert worker["account_id"] == "account-1"
    assert worker["worker_name"] == "sicurre-example"
    assert worker["scan_url"] == "https://api.sicurre.test/v1/email/scan"
    assert worker["forward_to"] == "inbox@example.test"
    assert len(worker["shared_secret"]) >= 40

    _, secret_params = queries.one("SET shared_secret_hash=?")
    assert secret_params[0] == hashlib.sha256(worker["shared_secret"].encode()).hexdigest()
    assert secret_params[1] == "enc:payload-token"
    assert secret_params[3] == "integration-1"
    _assert_resync_writes(queries)

    assert response == {
        "integration_id": "integration-1",
        "status": "active",
        "zone_name": ZONE,
        "destination_email": "inbox@example.test",
        "dns_sync": {"zone_id": "zone-1", "reputation_score": 100, "score_grade": "A"},
        "worker_update": {
            "updated": True,
            "scan_url": "https://api.sicurre.test/v1/email/scan",
            "worker_name": "sicurre-example",
        },
        "message": "Domain Shield DNS configuration applied.",
    }


@pytest.mark.asyncio
async def test_a_failed_worker_redeploy_records_the_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the Worker upload fails, the DNS work stays and the row carries the error."""
    queries = _Queries({"SELECT * FROM cloudflare_integration": [_connected_row()]})
    provisioner, _log = _provisioner(
        worker_error=integrations.CloudflareAPIError("Workers: script too large")
    )
    _patch(monkeypatch, queries, provisioner)

    with pytest.raises(HTTPException) as exc_info:
        await _setup(_payload(), BackgroundTasks(), _request(), _user())

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Cloudflare Worker update failed: Workers: script too large"
    _, params = queries.one("UPDATE cloudflare_integration SET error_message=?")
    assert params[0] == "Workers: script too large"
    assert params[1] == "enc:payload-token"
    assert params[3] == "integration-1"
    assert queries.matching("SET shared_secret_hash=?") == []
    assert queries.matching("INSERT INTO app_cloudflare_config") == []
    assert queries.matching("INSERT INTO app_alert_history") == []


@pytest.mark.asyncio
async def test_a_connected_domain_without_a_gateway_skips_the_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row that never got its Worker only receives the DNS sync."""
    row = _connected_row(account_id="", worker_name="")
    queries = _Queries({"SELECT * FROM cloudflare_integration": [row]})
    provisioner, log = _provisioner()
    _patch(monkeypatch, queries, provisioner)

    response = await _setup(_payload(), BackgroundTasks(), _request(), _user())

    assert log.workers == []
    assert queries.matching("SET shared_secret_hash=?") == []
    _assert_resync_writes(queries)
    assert response["worker_update"] is None
    assert response["status"] == "active"
    assert response["dns_sync"]["zone_id"] == "zone-1"


# --------------------------------------------------------------------------- New integrations


@pytest.mark.asyncio
async def test_a_failed_dns_sync_on_a_new_domain_marks_the_row_as_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The provisioning row is flipped to error and nothing is scheduled."""
    queries = _Queries()
    provisioner, _log = _provisioner()
    _patch(monkeypatch, queries, provisioner, sync=_sync_failing)
    background = BackgroundTasks()

    with pytest.raises(HTTPException) as exc_info:
        await _setup(_payload(), background, _request(), _user())

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == (
        "Cloudflare DNS update failed: DNS: Edit permission is missing"
    )
    _, insert_params = queries.one("INSERT INTO cloudflare_integration")
    _, config_params = queries.one("INSERT INTO app_cloudflare_config")
    assert config_params[1] == "enc:payload-token"
    _, error_params = queries.one("SET status='error', error_message=?")
    assert error_params[0] == "DNS: Edit permission is missing"
    assert error_params[2] == insert_params[0]
    assert background.tasks == []


@pytest.mark.asyncio
async def test_a_new_integration_inserts_a_provisioning_row_and_schedules_the_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The route answers before Cloudflare is touched for real."""
    queries = _Queries()
    provisioner, log = _provisioner()
    _patch(monkeypatch, queries, provisioner)
    background = BackgroundTasks()

    response = await _setup(_payload(), background, _request(), _user())

    _, insert_params = queries.one("INSERT INTO cloudflare_integration")
    assert insert_params[1:4] == ("owner@example.test", "workspace-1", "user-1")
    assert insert_params[5] == ZONE
    assert insert_params[9] == "inbox@example.test"
    assert insert_params[10] == "enc:payload-token"
    assert insert_params[12] == "provisioning"
    assert response == {
        "integration_id": insert_params[0],
        "status": "provisioning",
        "zone_name": ZONE,
        "destination_email": "inbox@example.test",
        "dns_sync": {"zone_id": "zone-1", "reputation_score": 100, "score_grade": "A"},
        "message": (
            "Provisioning started. Poll /v1/integrations/cloudflare/status to track progress."
        ),
    }
    assert len(background.tasks) == 1
    assert log.provisions == [], "provisioning must wait for the background task"


# --------------------------------------------------------------------------- Background task


async def _run_setup_and_task(payload: CloudflareSetupRequest) -> tuple[str, BackgroundTasks]:
    background = BackgroundTasks()
    response = await _setup(payload, background, _request(), _user())
    await background.tasks[0]()
    return response["integration_id"], background


@pytest.mark.asyncio
async def test_a_verified_destination_activates_the_integration(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The gateway result lands on the row as active and the alert is raised."""
    queries = _Queries()
    provisioner, log = _provisioner(result=_result(destination_verified=True))
    _patch(monkeypatch, queries, provisioner)
    caplog.set_level(logging.INFO, logger=cloudflare_onboarding.logger.name)

    integration_id, _ = await _run_setup_and_task(_payload())

    assert log.provisions == [
        {
            "zone_name": ZONE,
            "destination_email": "inbox@example.test",
            "scan_url": "https://api.sicurre.test/v1/email/scan",
        }
    ]
    _, params = queries.one("SET zone_id=?, account_id=?, worker_name=?, rule_id=?")
    assert params[:7] == (
        "zone-1",
        "account-1",
        "sicurre-example",
        "rule-1",
        "inbox@example.test",
        "hash-1",
        "active",
    )
    assert params[8] == integration_id
    _, alert_params = queries.one("INSERT INTO app_alert_history")
    assert alert_params[1:5] == (
        "workspace-1",
        ZONE,
        "Configuration Cloudflare appliquée",
        f"{ZONE} est synchronisé avec Cloudflare.",
    )
    assert alert_params[5] == params[7]
    assert f"Cloudflare provisioning complete for zone {ZONE}" in caplog.text
    assert queries.matching("status='error'") == []


@pytest.mark.asyncio
async def test_an_unverified_destination_waits_for_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a verified inbox the row stays pending; the scan URL comes from the request."""
    queries = _Queries()
    provisioner, log = _provisioner(result=_result(destination_verified=False))
    _patch(monkeypatch, queries, provisioner, settings=_settings(public_api_url=None))

    await _run_setup_and_task(_payload())

    assert log.provisions[0]["scan_url"] == "http://testserver/v1/email/scan"
    _, params = queries.one("SET zone_id=?, account_id=?, worker_name=?, rule_id=?")
    assert params[6] == "pending_verification"
    assert len(queries.matching("INSERT INTO app_alert_history")) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("records", "fix_spf", "fix_dmarc", "deployed", "expected"),
    [
        pytest.param(
            [
                _txt(ZONE, SPF_EXISTING),
                _txt(f"cf._domainkey.{ZONE}", DKIM_EXISTING),
                _txt(f"_dmarc.{ZONE}", DMARC_OWN_REJECT),
            ],
            True,
            True,
            [(ZONE, SPF_MERGED, "v=spf1"), (f"_dmarc.{ZONE}", DMARC_OWN_REJECT_MERGED, "v=DMARC1")],
            {
                "spf_valid": 1,
                "spf_record": SPF_MERGED,
                "dkim_valid": 1,
                "dkim_record": DKIM_EXISTING,
                "dmarc_valid": 1,
                "dmarc_record": DMARC_OWN_REJECT_MERGED,
                "dmarc_policy": "reject",
                "reputation_score": 100,
                "score_grade": "A",
            },
            id="both-fixes-keep-reject-and-add-reporting",
        ),
        pytest.param(
            [],
            True,
            True,
            [
                (ZONE, SPF_FROM_NOTHING, "v=spf1"),
                (f"_dmarc.{ZONE}", DMARC_SICURRE_REJECT, "v=DMARC1"),
            ],
            {
                "spf_valid": 1,
                "spf_record": SPF_FROM_NOTHING,
                "dkim_valid": 0,
                "dkim_record": None,
                "dmarc_valid": 1,
                "dmarc_record": DMARC_SICURRE_REJECT,
                "dmarc_policy": "reject",
                "reputation_score": 80,
                "score_grade": "B",
            },
            id="both-fixes-on-an-empty-zone",
        ),
        pytest.param(
            [
                _txt(ZONE, SPF_EXISTING),
                _txt(f"cf._domainkey.{ZONE}", DKIM_EXISTING),
                _txt(f"_dmarc.{ZONE}", DMARC_SICURRE_QUARANTINE),
            ],
            True,
            True,
            [
                (ZONE, SPF_MERGED, "v=spf1"),
                (f"_dmarc.{ZONE}", DMARC_SICURRE_QUARANTINE, "v=DMARC1"),
            ],
            {
                "spf_valid": 1,
                "spf_record": SPF_MERGED,
                "dkim_valid": 1,
                "dkim_record": DKIM_EXISTING,
                "dmarc_valid": 1,
                "dmarc_record": DMARC_SICURRE_QUARANTINE,
                "dmarc_policy": "quarantine",
                "reputation_score": 100,
                "score_grade": "A",
            },
            id="both-fixes-keep-quarantine",
        ),
        pytest.param(
            [
                _txt(ZONE, SPF_EXISTING),
                _txt(f"cf._domainkey.{ZONE}", DKIM_EXISTING),
                _txt(f"_dmarc.{ZONE}", "v=DMARC1; p=none"),
            ],
            False,
            True,
            [(f"_dmarc.{ZONE}", DMARC_SICURRE_QUARANTINE, "v=DMARC1")],
            {
                "spf_valid": 1,
                "spf_record": SPF_EXISTING,
                "dkim_valid": 1,
                "dkim_record": DKIM_EXISTING,
                "dmarc_valid": 1,
                "dmarc_record": DMARC_SICURRE_QUARANTINE,
                "dmarc_policy": "quarantine",
                "reputation_score": 100,
                "score_grade": "A",
            },
            id="dmarc-fix-only-raises-none-to-quarantine",
        ),
        pytest.param(
            [
                _txt(ZONE, SPF_EXISTING),
                _txt(f"_dmarc.{ZONE}", DMARC_SICURRE_REJECT),
            ],
            True,
            False,
            [(ZONE, SPF_MERGED, "v=spf1")],
            {
                "spf_valid": 1,
                "spf_record": SPF_MERGED,
                "dkim_valid": 0,
                "dkim_record": None,
                "dmarc_valid": 1,
                "dmarc_record": DMARC_SICURRE_REJECT,
                "dmarc_policy": "reject",
                "reputation_score": 80,
                "score_grade": "B",
            },
            id="spf-fix-only-without-dkim",
        ),
        pytest.param(
            [
                _txt(ZONE, SPF_EXISTING),
                _txt(f"cf._domainkey.{ZONE}", DKIM_EXISTING),
                _txt(f"_dmarc.{ZONE}", "v=DMARC1; p=none; rua=mailto:owner@example.test"),
            ],
            False,
            False,
            [],
            {
                "spf_valid": 1,
                "spf_record": SPF_EXISTING,
                "dkim_valid": 1,
                "dkim_record": DKIM_EXISTING,
                "dmarc_valid": 1,
                "dmarc_record": "v=DMARC1; p=none; rua=mailto:owner@example.test",
                "dmarc_policy": "none",
                "reputation_score": 90,
                "score_grade": "A",
            },
            id="no-fixes-own-reporting-only",
        ),
        pytest.param(
            [
                _txt(ZONE, SPF_EXISTING),
                _txt(f"cf._domainkey.{ZONE}", DKIM_EXISTING),
            ],
            False,
            False,
            [],
            {
                "spf_valid": 1,
                "spf_record": SPF_EXISTING,
                "dkim_valid": 1,
                "dkim_record": DKIM_EXISTING,
                "dmarc_valid": 0,
                "dmarc_record": None,
                "dmarc_policy": "none",
                "reputation_score": 75,
                "score_grade": "C",
            },
            id="no-fixes-missing-dmarc",
        ),
        pytest.param(
            [_txt(f"_dmarc.{ZONE}", DMARC_SICURRE_REJECT)],
            False,
            False,
            [],
            {
                "spf_valid": 0,
                "spf_record": None,
                "dkim_valid": 0,
                "dkim_record": None,
                "dmarc_valid": 1,
                "dmarc_record": DMARC_SICURRE_REJECT,
                "dmarc_policy": "reject",
                "reputation_score": 60,
                "score_grade": "D",
            },
            id="no-fixes-dmarc-only",
        ),
        pytest.param(
            [],
            False,
            False,
            [],
            {
                "spf_valid": 0,
                "spf_record": None,
                "dkim_valid": 0,
                "dkim_record": None,
                "dmarc_valid": 0,
                "dmarc_record": None,
                "dmarc_policy": "none",
                "reputation_score": 35,
                "score_grade": "F",
            },
            id="no-fixes-empty-zone",
        ),
    ],
)
async def test_the_background_task_applies_the_consented_fixes_and_scores_the_zone(
    monkeypatch: pytest.MonkeyPatch,
    records: list[dict[str, str]],
    fix_spf: bool,
    fix_dmarc: bool,
    deployed: list[tuple[str, str, str]],
    expected: dict[str, Any],
) -> None:
    """Only the consented records are written, and the score reflects the zone as left."""
    queries = _Queries()
    provisioner, log = _provisioner(records=records, result=_result(destination_verified=True))
    _patch(monkeypatch, queries, provisioner)

    await _run_setup_and_task(_payload(fix_spf=fix_spf, fix_dmarc=fix_dmarc))

    assert [(d["name"], d["content"], d["match_prefix"]) for d in log.deployed] == deployed
    assert all(d["zone_id"] == "zone-1" and d["rec_type"] == "TXT" for d in log.deployed)

    sql, params = queries.one("INSERT INTO app_domain_shield_status")
    columns = _column_names(sql)
    assert len(columns) == len(params)
    written = dict(zip(columns, params, strict=True))
    assert written["domain"] == ZONE
    assert written["workspace_id"] == "workspace-1"
    assert written["ssl_valid"] == 1
    assert written["ssl_days_remaining"] == 30
    for column, value in expected.items():
        assert written[column] == value, column
    _, status_params = queries.one("SET zone_id=?, account_id=?, worker_name=?, rule_id=?")
    assert written["updated_at"] == status_params[7]


@pytest.mark.asyncio
async def test_a_dns_read_failure_after_provisioning_keeps_the_gateway(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """DNS health is not gateway provisioning: the row stays active and the alert is raised."""
    queries = _Queries()
    provisioner, log = _provisioner(
        result=_result(destination_verified=True),
        records_error=RuntimeError("zone listing timed out"),
    )
    _patch(monkeypatch, queries, provisioner)
    caplog.set_level(logging.WARNING, logger=cloudflare_onboarding.logger.name)

    await _run_setup_and_task(_payload(fix_spf=True, fix_dmarc=True))

    assert log.deployed == []
    assert queries.matching("INSERT INTO app_domain_shield_status") == []
    _, params = queries.one("SET zone_id=?, account_id=?, worker_name=?, rule_id=?")
    assert params[6] == "active"
    assert len(queries.matching("INSERT INTO app_alert_history")) == 1
    assert queries.matching("status='error'") == []
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].getMessage() == (
        "Cloudflare gateway provisioned, but Domain Shield DNS sync failed for "
        f"{ZONE}: zone listing timed out"
    )


@pytest.mark.asyncio
async def test_a_failed_provision_marks_the_integration_as_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A provider failure in the background lands on the row for the UI to show."""
    queries = _Queries()
    provisioner, log = _provisioner(
        result=integrations.CloudflareAPIError("Email Routing: Edit permission is missing")
    )
    _patch(monkeypatch, queries, provisioner)
    caplog.set_level(logging.ERROR, logger=cloudflare_onboarding.logger.name)

    integration_id, _ = await _run_setup_and_task(_payload())

    assert len(log.provisions) == 1
    _, params = queries.one("SET status='error', error_message=?")
    assert params[0] == "Email Routing: Edit permission is missing"
    assert params[2] == integration_id
    assert queries.matching("SET zone_id=?") == []
    assert queries.matching("INSERT INTO app_alert_history") == []
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].getMessage() == (
        "Cloudflare provisioning failed: Email Routing: Edit permission is missing"
    )
    assert errors[0].exc_info is not None
