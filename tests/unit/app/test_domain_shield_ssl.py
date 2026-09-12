"""Domain Shield reports the certificate it measured, never one it assumed.

Auto-configuration used to stamp `ssl_valid=1, ssl_days_remaining=365` into the
status cache without opening a connection. The cached read then aged that
number down a day at a time, so a mail-only domain serving no HTTPS was
reported as holding a healthy certificate for a year - until someone happened
to press refresh, which measures for real.
"""

from __future__ import annotations

import inspect
import ssl
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from core.tls_certificate import CERTIFICATE_UNAVAILABLE, get_ssl_expiry_days
from data_platform.api.routers import integrations


def _shield_user() -> Any:
    """A workspace owner, the caller Domain Shield status is scoped to."""
    from data_platform.api.auth import AuthUser

    return AuthUser(
        id="user-1",
        email="owner@example.test",
        display_name="Owner",
        role="owner",
        workspace_id="workspace-1",
        workspace_name="Workspace",
        is_platform_admin=False,
    )


def _notafter(days_from_now: int) -> str:
    """Render an expiry the way OpenSSL does."""
    moment = datetime.now(timezone.utc) + timedelta(days=days_from_now, hours=1)
    return moment.strftime("%b %d %H:%M:%S %Y GMT")


class _FakeSocket:
    def __enter__(self) -> _FakeSocket:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class _FakeTLSSocket(_FakeSocket):
    def __init__(self, certificate: dict[str, Any] | None) -> None:
        self._certificate = certificate

    def getpeercert(self) -> dict[str, Any] | None:
        return self._certificate


def _patch_handshake(monkeypatch: pytest.MonkeyPatch, certificate: dict[str, Any] | None) -> None:
    """Serve a certificate without touching the network."""

    class _Context:
        def wrap_socket(self, _sock: object, server_hostname: str = "") -> _FakeTLSSocket:
            return _FakeTLSSocket(certificate)

    monkeypatch.setattr("core.tls_certificate.socket.create_connection", lambda *_a, **_k: _FakeSocket())
    monkeypatch.setattr("core.tls_certificate.ssl.create_default_context", _Context)


def test_a_live_certificate_reports_its_own_lifetime(monkeypatch: pytest.MonkeyPatch) -> None:
    """The number returned comes from the certificate, not from a constant."""
    _patch_handshake(monkeypatch, {"notAfter": _notafter(90)})
    assert get_ssl_expiry_days("example.test") == 90


def test_an_expired_certificate_is_not_reported_as_negative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Days remaining floors at zero; the caller reads it as expired."""
    _patch_handshake(monkeypatch, {"notAfter": _notafter(-30)})
    assert get_ssl_expiry_days("example.test") == 0


def test_a_certificate_without_an_expiry_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A peer certificate we cannot date tells us nothing about its lifetime."""
    _patch_handshake(monkeypatch, {})
    assert get_ssl_expiry_days("example.test") == CERTIFICATE_UNAVAILABLE


def test_no_certificate_at_all_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unverified peer returns nothing from getpeercert()."""
    _patch_handshake(monkeypatch, None)
    assert get_ssl_expiry_days("example.test") == CERTIFICATE_UNAVAILABLE


def test_an_unreachable_host_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A mail-only domain closing port 443 is a legitimate configuration."""

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr("core.tls_certificate.socket.create_connection", refuse)
    assert get_ssl_expiry_days("example.test") == CERTIFICATE_UNAVAILABLE


def test_a_chain_that_does_not_verify_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A self-signed certificate is not silently accepted."""

    class _Context:
        def wrap_socket(self, _sock: object, server_hostname: str = "") -> None:
            raise ssl.SSLCertVerificationError("self-signed certificate")

    monkeypatch.setattr(
        "core.tls_certificate.socket.create_connection", lambda *_a, **_k: _FakeSocket()
    )
    monkeypatch.setattr("core.tls_certificate.ssl.create_default_context", _Context)
    assert get_ssl_expiry_days("example.test") == CERTIFICATE_UNAVAILABLE


def test_the_handshake_really_verifies_the_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inspect the context the probe actually builds, not a stand-in for it.

    Turning verification off would make every self-signed or expired
    certificate look healthy, so this asserts against the real object rather
    than a fake that cannot tell the difference.
    """
    built: list[ssl.SSLContext] = []
    real_context = ssl.create_default_context

    def record() -> ssl.SSLContext:
        context = real_context()
        built.append(context)
        return context

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr("core.tls_certificate.ssl.create_default_context", record)
    monkeypatch.setattr("core.tls_certificate.socket.create_connection", refuse)

    get_ssl_expiry_days("example.test")

    assert built, "the probe built no TLS context"
    assert built[0].verify_mode is ssl.CERT_REQUIRED, "certificate verification is off"
    assert built[0].check_hostname is True, "hostname checking is off"


@pytest.mark.asyncio
async def test_the_write_path_records_what_it_measured(monkeypatch: pytest.MonkeyPatch) -> None:
    """A measured lifetime reaches the status cache unchanged."""
    monkeypatch.setattr(integrations, "get_ssl_expiry_days", lambda _domain: 77)
    assert await integrations._measure_ssl("vinse.app") == (1, 77)


@pytest.mark.asyncio
async def test_an_uninspectable_domain_is_not_credited_with_a_lifetime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression: no certificate must never become a year of validity."""
    monkeypatch.setattr(
        integrations, "get_ssl_expiry_days", lambda _domain: CERTIFICATE_UNAVAILABLE
    )
    assert await integrations._measure_ssl("mail-only.test") == (0, 0)


def test_auto_configuration_never_stamps_a_certificate_lifetime() -> None:
    """Guard: both status upserts bind SSL from the measurement, not a literal."""
    source = inspect.getsource(integrations)
    assert "1, 365" not in source, "a fabricated certificate lifetime is back in the write path"

    upserts = source.count("INSERT INTO app_domain_shield_status")
    assert upserts == 2, f"a new status upsert appeared ({upserts}); check how it sets SSL"
    assert source.count("await _measure_ssl(") == upserts, (
        "every status upsert must measure the certificate before it writes"
    )


def test_both_paths_take_the_measurement_from_the_same_place() -> None:
    """Refresh and auto-configuration cannot drift apart on how SSL is read."""
    from data_platform.api.routers import app_routes

    assert app_routes.get_ssl_expiry_days is get_ssl_expiry_days
    assert integrations.get_ssl_expiry_days is get_ssl_expiry_days


@pytest.mark.asyncio
async def test_the_cached_read_gives_the_same_reason_as_a_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row we could not inspect must not come back as invalid with no reason."""
    from data_platform.api.routers import app_routes

    row = {
        "spf_valid": 1, "spf_record": "v=spf1 -all",
        "dkim_valid": 0, "dkim_record": None,
        "dmarc_valid": 1, "dmarc_record": "v=DMARC1; p=reject", "dmarc_policy": "reject",
        "ssl_valid": 0, "ssl_days_remaining": 0,
        "reputation_score": 80, "score_grade": "B",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    async def allow(_domain: str, _workspace_id: str) -> None:
        return None

    async def blocklists(_domain: str, **_kwargs: object) -> tuple[list[str], list[str]]:
        return [], []

    async def query(_sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return [row]

    monkeypatch.setattr(app_routes, "_require_workspace_domain", allow)
    monkeypatch.setattr(app_routes, "_check_domain_blacklists", blocklists)
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    result = await app_routes.check_domain_shield_status(
        "mail-only.test", refresh=False, current_user=_shield_user()
    )

    assert result["ssl"] == {
        "valid": False,
        "days_remaining": 0,
        "auto_renew": False,
        "error": "Unable to inspect the public certificate",
    }


@pytest.mark.asyncio
async def test_a_healthy_cached_certificate_carries_no_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reason appears only when there is one; a live certificate is clean."""
    from data_platform.api.routers import app_routes

    row = {
        "spf_valid": 1, "spf_record": "v=spf1 -all",
        "dkim_valid": 1, "dkim_record": "v=DKIM1; p=abc",
        "dmarc_valid": 1, "dmarc_record": "v=DMARC1; p=reject", "dmarc_policy": "reject",
        "ssl_valid": 1, "ssl_days_remaining": 77,
        "reputation_score": 100, "score_grade": "A",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    async def allow(_domain: str, _workspace_id: str) -> None:
        return None

    async def blocklists(_domain: str, **_kwargs: object) -> tuple[list[str], list[str]]:
        return [], []

    async def query(_sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return [row]

    monkeypatch.setattr(app_routes, "_require_workspace_domain", allow)
    monkeypatch.setattr(app_routes, "_check_domain_blacklists", blocklists)
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    result = await app_routes.check_domain_shield_status(
        "vinse.app", refresh=False, current_user=_shield_user()
    )

    assert result["ssl"] == {
        "valid": True,
        "days_remaining": 77,
        "auto_renew": True,
        "error": None,
    }


class _StubProvisioner:
    """A zone whose records are already correct, so nothing is deployed."""

    def __init__(self, records: list[dict[str, str]]) -> None:
        self._records = records
        self.deployed: list[dict[str, Any]] = []

    async def get_zone(self, _zone_name: str) -> tuple[str, str]:
        return "zone-123", "active"

    async def get_dns_records(self, _zone_id: str) -> list[dict[str, str]]:
        return self._records

    async def deploy_dns_record(self, **kwargs: Any) -> None:
        self.deployed.append(kwargs)


def _column_names(sql: str) -> list[str]:
    """The column list of the INSERT, in the order the values bind to it."""
    inner = sql.split("app_domain_shield_status (", 1)[1].split(")", 1)[0]
    return [name.strip() for name in inner.replace("\n", " ").split(",")]


@pytest.mark.asyncio
async def test_the_measurement_lands_in_the_ssl_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bind every column to its value: two params were inserted mid-tuple.

    Positional `?` binding gives no error if `ssl_valid` is written one slot
    off — it would silently land in `reputation_score`. This pairs the INSERT's
    own column list with the parameters actually passed.
    """
    captured: dict[str, Any] = {}

    async def capture(sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
        if "app_domain_shield_status" in sql:
            captured["sql"] = sql
            captured["params"] = params
        return []

    monkeypatch.setattr(integrations, "_async_query", capture)
    monkeypatch.setattr(integrations, "get_ssl_expiry_days", lambda _domain: 77)

    # A fully configured zone, so every column has a distinctive value.
    records = [
        {"type": "TXT", "name": "example.test", "content": "v=spf1 -all"},
        {
            "type": "TXT",
            "name": "cf2024-1._domainkey.example.test",
            "content": "v=DKIM1; k=rsa; p=" + "MIIBIjANBgkqhkiG9w0BAQEF" * 17,
        },
        {
            "type": "TXT",
            "name": "_dmarc.example.test",
            "content": "v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com",
        },
    ]
    await integrations._sync_domain_shield_dns(
        provisioner=_StubProvisioner(records),  # type: ignore[arg-type]
        workspace_id="workspace-1",
        zone_name="example.test",
        fix_spf=False,
        fix_dmarc=False,
    )

    columns = _column_names(captured["sql"])
    params = captured["params"]
    assert len(columns) == len(params), f"{len(columns)} columns, {len(params)} parameters"
    written = dict(zip(columns, params, strict=True))

    assert written["ssl_valid"] == 1
    assert written["ssl_days_remaining"] == 77
    # The neighbours the two new parameters could have displaced.
    assert written["dmarc_policy"] == "reject"
    assert written["reputation_score"] == 100
    assert written["score_grade"] == "A"
    assert written["domain"] == "example.test"
    assert written["workspace_id"] == "workspace-1"


@pytest.mark.asyncio
async def test_an_uninspectable_domain_is_written_as_uninspected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end: no certificate reaches the row as (0, 0), never (1, 365)."""
    captured: dict[str, Any] = {}

    async def capture(sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
        if "app_domain_shield_status" in sql:
            captured["sql"] = sql
            captured["params"] = params
        return []

    monkeypatch.setattr(integrations, "_async_query", capture)
    monkeypatch.setattr(
        integrations, "get_ssl_expiry_days", lambda _domain: CERTIFICATE_UNAVAILABLE
    )

    await integrations._sync_domain_shield_dns(
        provisioner=_StubProvisioner([]),  # type: ignore[arg-type]
        workspace_id="workspace-1",
        zone_name="mail-only.test",
        fix_spf=False,
        fix_dmarc=False,
    )

    written = dict(zip(_column_names(captured["sql"]), captured["params"], strict=True))
    assert written["ssl_valid"] == 0
    assert written["ssl_days_remaining"] == 0


@pytest.mark.asyncio
async def test_a_cached_certificate_that_has_run_out_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aged-out and never-inspected are different facts, and read differently.

    The cache ages `days_remaining` down from the day it was measured. Reaching
    zero means the certificate we did see has since expired - not that we could
    not see one - so it must not borrow the uninspectable wording.
    """
    from data_platform.api.routers import app_routes

    measured_at = datetime.now(timezone.utc) - timedelta(days=120)
    row = {
        "spf_valid": 1, "spf_record": "v=spf1 -all",
        "dkim_valid": 1, "dkim_record": "v=DKIM1; p=abc",
        "dmarc_valid": 1, "dmarc_record": "v=DMARC1; p=reject", "dmarc_policy": "reject",
        "ssl_valid": 1, "ssl_days_remaining": 30,   # 30 days left, measured 120 days ago
        "reputation_score": 100, "score_grade": "A",
        "updated_at": measured_at.isoformat(),
    }

    async def allow(_domain: str, _workspace_id: str) -> None:
        return None

    async def blocklists(_domain: str, **_kwargs: object) -> tuple[list[str], list[str]]:
        return [], []

    async def query(_sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return [row]

    monkeypatch.setattr(app_routes, "_require_workspace_domain", allow)
    monkeypatch.setattr(app_routes, "_check_domain_blacklists", blocklists)
    monkeypatch.setattr(app_routes, "async_query_auth_db", query)

    result = await app_routes.check_domain_shield_status(
        "lapsed.test", refresh=False, current_user=_shield_user()
    )

    assert result["ssl"] == {
        "valid": False,
        "days_remaining": 0,
        "auto_renew": False,
        "error": "The measured certificate has expired",
    }


@pytest.mark.asyncio
async def test_the_selected_fixes_write_the_merged_records_and_the_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both fixes on: the merged SPF and DMARC are deployed and the row reflects them."""
    captured: dict[str, Any] = {}

    async def capture(sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
        if "app_domain_shield_status" in sql:
            captured["sql"] = sql
            captured["params"] = params
        return []

    monkeypatch.setattr(integrations, "_async_query", capture)
    monkeypatch.setattr(integrations, "get_ssl_expiry_days", lambda _domain: 30)
    provisioner = _StubProvisioner(
        [
            {"type": "TXT", "name": "example.test", "content": "v=spf1 include:_spf.google.com -all"},
            {"type": "TXT", "name": "_dmarc.example.test", "content": "v=DMARC1; p=none"},
        ]
    )

    result = await integrations._sync_domain_shield_dns(
        provisioner=provisioner,  # type: ignore[arg-type]
        workspace_id="workspace-1",
        zone_name="example.test",
        fix_spf=True,
        fix_dmarc=True,
    )

    deployed = {record["name"]: record["content"] for record in provisioner.deployed}
    assert deployed == {
        "example.test": "v=spf1 include:_spf.google.com include:_spf.mx.cloudflare.net -all",
        "_dmarc.example.test": "v=DMARC1; p=quarantine; rua=mailto:dmarc@sicurre.com",
    }
    assert result["dmarc_reporting_enabled"] is True
    written = dict(zip(_column_names(captured["sql"]), captured["params"], strict=True))
    assert (written["spf_valid"], written["dkim_valid"], written["dmarc_valid"]) == (1, 0, 1)
    assert written["dmarc_policy"] == "quarantine"
    assert (written["reputation_score"], written["score_grade"]) == (80, "B")
