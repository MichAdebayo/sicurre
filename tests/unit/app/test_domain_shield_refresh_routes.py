"""Domain Shield refresh and DMARC summary routes, driven directly.

The refresh route resolves SPF, DKIM and DMARC over DNS, measures the public
certificate, keeps an SCD Type 2 history and raises a Loops alert when the
score drops. Every external edge is stubbed here: the DNS resolver, the
certificate probe, the Cloudflare provisioner behind the stored token, the
auth database and the Loops client.
"""

from __future__ import annotations

import gzip
import io
import zipfile
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import dns.resolver
import pytest
from fastapi import HTTPException

from data_platform.api import workspace_scope
from data_platform.api.auth import AuthUser
from data_platform.api.routers import dmarc_reports, domain_shield

DOMAIN = "example.test"


def _owner() -> AuthUser:
    return AuthUser(
        id="user-1",
        email="owner@example.test",
        display_name="Owner Name",
        role="owner",
        workspace_id="workspace-1",
        workspace_name="Workspace",
        is_platform_admin=False,
    )


def _nameless_owner() -> AuthUser:
    return AuthUser(
        id="user-2",
        email="owner@example.test",
        display_name="",
        role="owner",
        workspace_id="workspace-1",
        workspace_name="Workspace",
        is_platform_admin=False,
    )


class _TxtAnswer:
    """One TXT rdata the way dnspython exposes it: a tuple of byte chunks."""

    def __init__(self, *chunks: bytes | str) -> None:
        self.strings = list(chunks)


class _FakeResolver:
    """A resolver keyed by (name, rrtype) that raises for anything unknown."""

    def __init__(self, records: dict[tuple[str, str], list[_TxtAnswer]]) -> None:
        self.records = records
        self.queries: list[tuple[str, str]] = []

    def __call__(self, name: str, rrtype: str) -> list[_TxtAnswer]:
        self.queries.append((name, rrtype))
        try:
            return self.records[(name, rrtype)]
        except KeyError as exc:
            raise dns.resolver.NXDOMAIN(f"{name} has no {rrtype}") from exc


class _FakeProvisioner:
    """Cloudflare stand-in exposing the two calls DKIM discovery relies on."""

    zone_raises = False
    dns_records: list[dict[str, Any]] = []
    instances: list[_FakeProvisioner] = []

    def __init__(self, api_token: str) -> None:
        self.api_token = api_token
        type(self).instances.append(self)

    async def get_zone(self, domain: str) -> tuple[str, str]:
        if type(self).zone_raises:
            raise RuntimeError("zone lookup failed")
        return "zone-1", domain

    async def get_dns_records(self, zone_id: str) -> list[dict[str, Any]]:
        assert zone_id == "zone-1"
        return list(type(self).dns_records)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        spamhaus_dqs_key=None,
        secret_encryption_key="test-key",
        environment="dev",
        loops_dns_shield_alert_transaction_id="tx-dns-shield",
        public_api_url="https://app.sicurre.test",
    )


def _install_refresh_edges(
    monkeypatch: pytest.MonkeyPatch,
    *,
    resolver: _FakeResolver,
    ssl_days: int = 42,
    blacklists: tuple[list[str], list[str]] = ([], []),
) -> None:
    """Route every collaborator of the refresh path to an in-memory stub."""

    async def allow(_domain: str, _workspace_id: str) -> None:
        return None

    async def blocklists(_domain: str, **_kwargs: object) -> tuple[list[str], list[str]]:
        return blacklists

    async def direct_call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    def expiry(_domain: str) -> int:
        return ssl_days

    monkeypatch.setattr(workspace_scope, "require_workspace_domain", allow)

    monkeypatch.setattr(domain_shield, "require_workspace_domain", allow)
    monkeypatch.setattr(domain_shield, "_check_domain_blacklists", blocklists)
    monkeypatch.setattr(domain_shield, "get_settings", _settings)
    monkeypatch.setattr(domain_shield.asyncio, "to_thread", direct_call)
    monkeypatch.setattr("dns.resolver.resolve", resolver)
    monkeypatch.setattr(domain_shield, "get_ssl_expiry_days", expiry)


def _query_factory(
    *,
    token_rows: list[dict[str, Any]] | None = None,
    history_rows: list[dict[str, Any]] | None = None,
    preference_rows: list[dict[str, Any]] | None = None,
    cached_rows: list[dict[str, Any]] | None = None,
) -> tuple[Callable[..., Any], list[tuple[str, tuple[Any, ...]]]]:
    """A fake auth query answering by SQL fragment and recording every write."""
    writes: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        normalized = " ".join(sql.split())
        if normalized.startswith("SELECT * FROM app_domain_shield_status"):
            return list(cached_rows or [])
        if normalized.startswith("SELECT api_token FROM app_cloudflare_config"):
            return list(token_rows or [])
        if normalized.startswith("SELECT * FROM app_domain_shield_history"):
            return list(history_rows or [])
        if normalized.startswith("SELECT * FROM app_alert_preference"):
            return list(preference_rows or [])
        writes.append((normalized, params))
        return []

    return query, writes


def _tables(writes: list[tuple[str, tuple[Any, ...]]]) -> list[str]:
    """The statement head of each recorded write: verb plus table name."""
    return [sql.split("(")[0].split(" SET ")[0].strip() for sql, _ in writes]


def _full_records(*, dkim_selector: str = "google") -> dict[tuple[str, str], list[_TxtAnswer]]:
    return {
        (DOMAIN, "TXT"): [
            _TxtAnswer(b"google-site-verification=abc"),
            _TxtAnswer(b"v=spf1 include:_spf.google.com ", b"-all"),
        ],
        (f"{dkim_selector}._domainkey.{DOMAIN}", "TXT"): [_TxtAnswer(b"v=DKIM1; k=rsa; p=MIIB")],
        (f"_dmarc.{DOMAIN}", "TXT"): [
            _TxtAnswer(b"v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com")
        ],
    }


# --------------------------------------------------------------------------- #
# DMARC parsing helpers
# --------------------------------------------------------------------------- #


def test_a_gzip_payload_is_inflated_before_parsing() -> None:
    xml = b"<feedback><report_metadata/></feedback>"

    assert dmarc_reports.extract_dmarc_xml_payload(gzip.compress(xml)) == xml


def test_a_zip_payload_yields_its_xml_member() -> None:
    xml = b"<feedback><report_metadata/></feedback>"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "ignored")
        archive.writestr("report.XML", xml)

    assert dmarc_reports.extract_dmarc_xml_payload(buffer.getvalue()) == xml


def test_a_zip_payload_without_an_xml_member_is_rejected() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "no report here")

    with pytest.raises(HTTPException) as excinfo:
        dmarc_reports.extract_dmarc_xml_payload(buffer.getvalue())

    assert excinfo.value.status_code == 400
    assert "does not contain" in excinfo.value.detail


def test_a_plain_payload_passes_through_untouched() -> None:
    xml = b"<feedback/>"

    assert dmarc_reports.extract_dmarc_xml_payload(xml) is xml


def test_text_or_none_handles_missing_nodes_children_and_empty_text() -> None:
    import xml.etree.ElementTree as ET

    node = ET.fromstring("<row><source_ip> 192.0.2.1 </source_ip><count/></row>")

    assert dmarc_reports._text_or_none(None, "source_ip") is None
    assert dmarc_reports._text_or_none(node, "missing") is None
    assert dmarc_reports._text_or_none(node, "count") is None
    assert dmarc_reports._text_or_none(node, "source_ip") == "192.0.2.1"


def test_epoch_to_iso_handles_empty_and_non_numeric_values() -> None:
    assert dmarc_reports._epoch_to_iso(None) is None
    assert dmarc_reports._epoch_to_iso("") is None
    assert dmarc_reports._epoch_to_iso("not-a-number") is None
    assert dmarc_reports._epoch_to_iso("0") == "1970-01-01T00:00:00+00:00"


def test_invalid_dmarc_xml_is_rejected_with_a_400() -> None:
    with pytest.raises(HTTPException) as excinfo:
        dmarc_reports._parse_dmarc_report(b"<feedback><unclosed>", DOMAIN)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid DMARC XML report"


def test_a_dmarc_report_for_another_domain_is_rejected() -> None:
    xml = b"<feedback><policy_published><domain>other.test</domain></policy_published></feedback>"

    with pytest.raises(HTTPException) as excinfo:
        dmarc_reports._parse_dmarc_report(xml, DOMAIN)

    assert excinfo.value.status_code == 400
    assert "does not match" in excinfo.value.detail


def test_a_dmarc_report_is_flattened_into_one_row_per_record() -> None:
    xml = f"""
    <feedback>
      <report_metadata>
        <org_name>google.com</org_name>
        <report_id>rid-1</report_id>
        <date_range><begin>0</begin><end>86400</end></date_range>
      </report_metadata>
      <policy_published><domain>{DOMAIN}</domain></policy_published>
      <record>
        <row>
          <source_ip>192.0.2.7</source_ip>
          <count>3</count>
          <policy_evaluated><disposition>quarantine</disposition></policy_evaluated>
        </row>
        <identifiers><header_from>{DOMAIN}</header_from></identifiers>
        <auth_results>
          <dkim><result>pass</result></dkim>
          <spf><result>fail</result></spf>
        </auth_results>
      </record>
      <record><row/></record>
    </feedback>
    """.encode()

    rows = dmarc_reports._parse_dmarc_report(xml, DOMAIN)

    assert len(rows) == 2
    assert rows[0] == {
        "report_org": "google.com",
        "report_id": "rid-1",
        "period_begin": "1970-01-01T00:00:00+00:00",
        "period_end": "1970-01-02T00:00:00+00:00",
        "source_ip": "192.0.2.7",
        "message_count": 3,
        "disposition": "quarantine",
        "dkim_result": "pass",
        "spf_result": "fail",
        "header_from": DOMAIN,
    }
    assert rows[1]["source_ip"] == "unknown"
    assert rows[1]["message_count"] == 0
    assert rows[1]["disposition"] == "none"
    assert rows[1]["dkim_result"] == "unknown"
    assert rows[1]["header_from"] == DOMAIN


# --------------------------------------------------------------------------- #
# DMARC summary route
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_dmarc_summary_aggregates_the_summary_row_and_top_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_params: list[tuple[Any, ...]] = []
    table_calls: list[str] = []

    async def allow(_domain: str, _workspace_id: str) -> None:
        return None

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        seen_params.append(params)
        if "GROUP BY source_ip" in sql:
            return [
                {
                    "source_ip": "192.0.2.7",
                    "message_count": "12",
                    "disposition": "none",
                    "dkim_result": "pass",
                    "spf_result": "pass",
                },
                {
                    "source_ip": "198.51.100.3",
                    "message_count": None,
                    "disposition": "reject",
                    "dkim_result": "fail",
                    "spf_result": "fail",
                },
            ]
        return [
            {
                "total_messages": 15,
                "aligned_messages": 12,
                "failed_messages": 3,
                "report_count": 2,
                "last_report_at": "2026-09-01T00:00:00Z",
            }
        ]

    monkeypatch.setattr(workspace_scope, "require_workspace_domain", allow)

    monkeypatch.setattr(dmarc_reports, "require_workspace_domain", allow)
    monkeypatch.setattr(
        dmarc_reports, "ensure_runtime_tables", lambda: table_calls.append("ensured")
    )
    monkeypatch.setattr(dmarc_reports, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await dmarc_reports.get_dmarc_report_summary(DOMAIN, current_user=_owner())

    assert table_calls == ["ensured"]
    assert seen_params == [("workspace-1", DOMAIN), ("workspace-1", DOMAIN)]
    assert result["domain"] == DOMAIN
    assert result["total_messages"] == 15
    assert result["aligned_messages"] == 12
    assert result["failed_messages"] == 3
    assert result["report_count"] == 2
    assert result["last_report_at"] == "2026-09-01T00:00:00Z"
    assert result["top_sources"] == [
        {
            "source_ip": "192.0.2.7",
            "message_count": 12,
            "disposition": "none",
            "dkim_result": "pass",
            "spf_result": "pass",
        },
        {
            "source_ip": "198.51.100.3",
            "message_count": 0,
            "disposition": "reject",
            "dkim_result": "fail",
            "spf_result": "fail",
        },
    ]


@pytest.mark.asyncio
async def test_dmarc_summary_without_any_rows_reports_zeroes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def allow(_domain: str, _workspace_id: str) -> None:
        return None

    async def query(_sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(workspace_scope, "require_workspace_domain", allow)

    monkeypatch.setattr(dmarc_reports, "require_workspace_domain", allow)
    monkeypatch.setattr(dmarc_reports, "ensure_runtime_tables", lambda: None)
    monkeypatch.setattr(dmarc_reports, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await dmarc_reports.get_dmarc_report_summary(DOMAIN, current_user=_owner())

    assert result == {
        "domain": DOMAIN,
        "total_messages": 0,
        "aligned_messages": 0,
        "failed_messages": 0,
        "report_count": 0,
        "last_report_at": None,
        "top_sources": [],
    }


# --------------------------------------------------------------------------- #
# Domain Shield cached read
# --------------------------------------------------------------------------- #


def _cached_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "spf_valid": 1,
        "spf_record": "v=spf1 -all",
        "dkim_valid": 1,
        "dkim_record": "v=DKIM1; p=abc",
        "dmarc_valid": 1,
        "dmarc_record": "v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com",
        "dmarc_policy": "reject",
        "ssl_valid": 1,
        "ssl_days_remaining": 90,
        "reputation_score": 100,
        "score_grade": "A",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    row.update(overrides)
    return row


def _install_cached_edges(
    monkeypatch: pytest.MonkeyPatch,
    row: dict[str, Any],
    blacklists: tuple[list[str], list[str]] = ([], []),
) -> None:
    async def allow(_domain: str, _workspace_id: str) -> None:
        return None

    async def blocklists(_domain: str, **_kwargs: object) -> tuple[list[str], list[str]]:
        return blacklists

    async def query(_sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return [row]

    monkeypatch.setattr(workspace_scope, "require_workspace_domain", allow)
    monkeypatch.setattr(domain_shield, "_check_domain_blacklists", blocklists)
    monkeypatch.setattr(domain_shield, "get_settings", _settings)
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)


@pytest.mark.asyncio
async def test_cached_certificate_days_age_down_by_the_elapsed_days(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A naive timestamp ten days old takes ten days off the cached remaining count."""
    measured_at = datetime.now(timezone.utc) - timedelta(days=10, hours=2)
    row = _cached_row(
        ssl_days_remaining=90,
        updated_at=measured_at.replace(tzinfo=None).isoformat() + "Z",
    )
    _install_cached_edges(monkeypatch, row)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=False, current_user=_owner()
    )

    assert result["ssl"] == {
        "valid": True,
        "days_remaining": 80,
        "auto_renew": True,
        "error": None,
    }
    assert result["spf"] == {"valid": True, "record": "v=spf1 -all", "error": None}
    assert result["dkim"] == {"valid": True, "record": "v=DKIM1; p=abc", "error": None}
    assert result["dmarc"]["reporting_enabled"] is True
    assert result["dmarc"]["policy"] == "reject"
    assert result["reputation_score"] == 100
    assert result["score_grade"] == "A"
    assert result["blacklists"] == {"listed": False, "matched": [], "error": None}
    assert result["updated_at"] == row["updated_at"]


@pytest.mark.asyncio
async def test_a_cached_certificate_that_ran_out_is_reported_as_expired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    measured_at = datetime.now(timezone.utc) - timedelta(days=5, hours=1)
    row = _cached_row(ssl_valid=1, ssl_days_remaining=3, updated_at=measured_at.isoformat())
    _install_cached_edges(monkeypatch, row)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=False, current_user=_owner()
    )

    assert result["ssl"] == {
        "valid": False,
        "days_remaining": 0,
        "auto_renew": False,
        "error": "The measured certificate has expired",
    }


@pytest.mark.asyncio
async def test_a_cached_certificate_never_measured_names_the_inspection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _cached_row(
        ssl_valid=0,
        ssl_days_remaining=0,
        spf_valid=0,
        spf_record=None,
        dkim_valid=0,
        dkim_record=None,
        dmarc_valid=0,
        dmarc_record=None,
        dmarc_policy=None,
        reputation_score=55,
        score_grade="F",
        updated_at="not-a-timestamp",
    )
    _install_cached_edges(monkeypatch, row)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=False, current_user=_owner()
    )

    assert result["ssl"]["error"] == "Unable to inspect the public certificate"
    assert result["spf"]["error"] == "Not configured"
    assert result["dkim"]["error"] == "Not configured"
    assert result["dmarc"] == {
        "valid": False,
        "record": None,
        "policy": "none",
        "reporting_enabled": False,
        "error": "Not configured",
    }
    assert result["score_grade"] == "F"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("cached_score", "listed", "expected_score", "expected_grade"),
    [
        (100, ["Spamhaus DBL"], 70, "C"),
        (95, ["SURBL List"], 65, "D"),
        (100, ["Spamhaus DBL", "SURBL List"], 40, "F"),
        (85, ["Spamhaus DBL"], 55, "F"),
        (100, [], 100, "A"),
        (85, [], 85, "B"),
    ],
)
async def test_a_blacklist_listing_lowers_the_cached_score_and_recomputes_the_grade(
    monkeypatch: pytest.MonkeyPatch,
    cached_score: int,
    listed: list[str],
    expected_score: int,
    expected_grade: str,
) -> None:
    row = _cached_row(reputation_score=cached_score, score_grade="?")
    _install_cached_edges(monkeypatch, row, blacklists=(listed, ["Spamhaus unreachable"]))

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=False, current_user=_owner()
    )

    assert result["reputation_score"] == expected_score
    assert result["score_grade"] == expected_grade
    assert result["blacklists"] == {
        "listed": bool(listed),
        "matched": listed,
        "error": "Spamhaus unreachable",
    }


# --------------------------------------------------------------------------- #
# Domain Shield refresh: DNS, certificate, history
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_a_fully_configured_domain_refreshes_to_a_perfect_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = _FakeResolver(_full_records())
    _install_refresh_edges(monkeypatch, resolver=resolver, ssl_days=42)
    query, writes = _query_factory()
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=True, current_user=_owner()
    )

    assert result["spf"] == {
        "valid": True,
        "record": "v=spf1 include:_spf.google.com -all",
        "error": None,
    }
    assert result["dkim"] == {"valid": True, "record": "v=DKIM1; k=rsa; p=MIIB", "error": None}
    assert result["dmarc"] == {
        "valid": True,
        "record": "v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com",
        "policy": "reject",
        "reporting_enabled": True,
        "error": None,
    }
    assert result["ssl"] == {
        "valid": True,
        "days_remaining": 42,
        "auto_renew": True,
        "error": None,
    }
    assert result["reputation_score"] == 100
    assert result["score_grade"] == "A"
    assert result["updated_at"].endswith("Z")

    # No history yet: the previous record is closed (no-op), one is opened, cache upserted.
    assert _tables(writes) == [
        "UPDATE app_domain_shield_history",
        "INSERT INTO app_domain_shield_history",
        "INSERT INTO app_domain_shield_status",
    ]
    history_params = writes[1][1]
    assert history_params[1:9] == ("workspace-1", DOMAIN, 100, "A", 1, 1, 1, 1)
    status_params = writes[2][1]
    assert status_params[:2] == (DOMAIN, "workspace-1")
    assert status_params[8] == "reject"
    assert status_params[10] == 42


@pytest.mark.asyncio
async def test_a_bare_domain_loses_points_for_every_missing_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPF, DKIM and DMARC lookups all fail; the certificate cannot be read."""
    resolver = _FakeResolver({})
    _install_refresh_edges(monkeypatch, resolver=resolver, ssl_days=-1)
    query, writes = _query_factory()
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=True, current_user=_owner()
    )

    assert result["spf"]["valid"] is False
    assert "has no TXT" in result["spf"]["error"]
    assert result["dkim"]["valid"] is False
    assert result["dkim"]["error"].startswith("DKIM record not found for selectors: cloudflare,")
    assert result["dmarc"]["valid"] is False
    assert "_dmarc.example.test has no TXT" in result["dmarc"]["error"]
    assert result["ssl"] == {
        "valid": False,
        "days_remaining": 0,
        "auto_renew": False,
        "error": "Unable to inspect the public certificate",
    }
    # 100 - 20 (SPF) - 20 (DKIM) - 25 (DMARC) = 35
    assert result["reputation_score"] == 35
    assert result["score_grade"] == "F"
    assert writes[1][1][3:9] == (35, "F", 0, 0, 0, 0)


@pytest.mark.asyncio
async def test_a_txt_answer_without_spf_leaves_spf_unconfigured_without_penalty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = _full_records()
    records[(DOMAIN, "TXT")] = [_TxtAnswer("google-site-verification=abc")]
    resolver = _FakeResolver(records)
    _install_refresh_edges(monkeypatch, resolver=resolver)
    query, _writes = _query_factory()
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=True, current_user=_owner()
    )

    assert result["spf"] == {"valid": False, "record": None, "error": "Not configured"}
    assert result["reputation_score"] == 100


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dmarc_txt", "expected_policy", "reporting", "expected_score", "expected_grade"),
    [
        ("v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com", "reject", True, 100, "A"),
        ("v=DMARC1; p=quarantine; rua=mailto:dmarc@sicurre.com", "quarantine", True, 100, "A"),
        ("v=DMARC1; p=none; rua=mailto:dmarc@sicurre.com", "none", True, 90, "A"),
        ("v=DMARC1; p=reject", "reject", False, 90, "A"),
        ("v=DMARC1; p=none", "none", False, 80, "B"),
    ],
)
async def test_the_dmarc_policy_and_reporting_address_shape_the_score(
    monkeypatch: pytest.MonkeyPatch,
    dmarc_txt: str,
    expected_policy: str,
    reporting: bool,
    expected_score: int,
    expected_grade: str,
) -> None:
    records = _full_records()
    records[(f"_dmarc.{DOMAIN}", "TXT")] = [
        _TxtAnswer(b"unrelated=txt"),
        _TxtAnswer(dmarc_txt.encode()),
    ]
    resolver = _FakeResolver(records)
    _install_refresh_edges(monkeypatch, resolver=resolver)
    query, _writes = _query_factory()
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=True, current_user=_owner()
    )

    assert result["dmarc"]["valid"] is True
    assert result["dmarc"]["record"] == dmarc_txt
    assert result["dmarc"]["policy"] == expected_policy
    assert result["dmarc"]["reporting_enabled"] is reporting
    assert result["reputation_score"] == expected_score
    assert result["score_grade"] == expected_grade


@pytest.mark.asyncio
async def test_a_dmarc_answer_without_a_dmarc_record_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = _full_records()
    records[(f"_dmarc.{DOMAIN}", "TXT")] = [_TxtAnswer(b"just-a-txt")]
    resolver = _FakeResolver(records)
    _install_refresh_edges(monkeypatch, resolver=resolver)
    query, _writes = _query_factory()
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=True, current_user=_owner()
    )

    assert result["dmarc"]["valid"] is False
    assert result["dmarc"]["error"] == "Not configured"
    assert result["reputation_score"] == 100


@pytest.mark.asyncio
async def test_dkim_is_found_on_a_later_selector_after_earlier_ones_answer_junk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A selector answering a non-DKIM TXT is skipped; k=rsa alone is accepted."""
    records = _full_records(dkim_selector="k1")
    records[(f"cloudflare._domainkey.{DOMAIN}", "TXT")] = [_TxtAnswer(b"nothing useful")]
    records[(f"k1._domainkey.{DOMAIN}", "TXT")] = [_TxtAnswer(b"k=rsa; p=MIIB")]
    resolver = _FakeResolver(records)
    _install_refresh_edges(monkeypatch, resolver=resolver)
    query, _writes = _query_factory()
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=True, current_user=_owner()
    )

    assert result["dkim"] == {"valid": True, "record": "k=rsa; p=MIIB", "error": None}
    queried = [name for name, _ in resolver.queries if "_domainkey" in name]
    assert queried[0] == f"cloudflare._domainkey.{DOMAIN}"
    assert queried[-1] == f"k1._domainkey.{DOMAIN}"


@pytest.mark.asyncio
async def test_a_stored_cloudflare_token_discovers_extra_dkim_selectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decrypted: list[tuple[str, dict[str, Any]]] = []

    def decrypt(value: str, **kwargs: Any) -> str:
        decrypted.append((value, kwargs))
        return "plain-token"

    monkeypatch.setattr(domain_shield, "decrypt_secret", decrypt)
    monkeypatch.setattr(_FakeProvisioner, "zone_raises", False)
    monkeypatch.setattr(
        _FakeProvisioner,
        "dns_records",
        [
            {"name": f"sel1._domainkey.{DOMAIN}", "type": "TXT"},
            {"name": f"sel1._domainkey.{DOMAIN}", "type": "TXT"},
            {"name": f"google._domainkey.{DOMAIN}", "type": "TXT"},
            {"name": f"cname._domainkey.{DOMAIN}", "type": "CNAME"},
            {"name": f"._domainkey.{DOMAIN}", "type": "TXT"},
            {"name": DOMAIN, "type": "A"},
            {"type": "TXT"},
        ],
    )
    monkeypatch.setattr(_FakeProvisioner, "instances", [])
    monkeypatch.setattr(
        "data_platform.services.cloudflare_provisioner.CloudflareProvisioner", _FakeProvisioner
    )

    records = _full_records(dkim_selector="sel1")
    resolver = _FakeResolver(records)
    _install_refresh_edges(monkeypatch, resolver=resolver)
    query, _writes = _query_factory(token_rows=[{"api_token": "enc:token"}])
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=True, current_user=_owner()
    )

    assert decrypted == [
        ("enc:token", {"configured_key": "test-key", "environment": "dev"}),
    ]
    assert [p.api_token for p in _FakeProvisioner.instances] == ["plain-token"]
    assert result["dkim"] == {"valid": True, "record": "v=DKIM1; k=rsa; p=MIIB", "error": None}
    queried = [name for name, _ in resolver.queries if "_domainkey" in name]
    # The discovered selector is appended once, after the defaults; "google" is
    # already a default and the empty-selector name is skipped.
    assert queried[-1] == f"sel1._domainkey.{DOMAIN}"
    assert queried.count(f"sel1._domainkey.{DOMAIN}") == 1
    assert queried.count(f"google._domainkey.{DOMAIN}") == 1
    assert f"._domainkey.{DOMAIN}" not in queried


@pytest.mark.asyncio
async def test_a_cache_miss_without_refresh_measures_the_domain_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = _FakeResolver(_full_records())
    _install_refresh_edges(monkeypatch, resolver=resolver, ssl_days=42)
    query, writes = _query_factory(cached_rows=[])
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=False, current_user=_owner()
    )

    assert result["reputation_score"] == 100
    assert resolver.queries[0] == (DOMAIN, "TXT")
    assert _tables(writes)[-1] == "INSERT INTO app_domain_shield_status"


@pytest.mark.asyncio
async def test_a_failing_cloudflare_zone_lookup_falls_back_to_the_default_selectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(domain_shield, "decrypt_secret", lambda value, **_kwargs: "plain-token")
    monkeypatch.setattr(_FakeProvisioner, "zone_raises", True)
    monkeypatch.setattr(_FakeProvisioner, "dns_records", [])
    monkeypatch.setattr(
        "data_platform.services.cloudflare_provisioner.CloudflareProvisioner", _FakeProvisioner
    )

    records = _full_records(dkim_selector="sel1")
    resolver = _FakeResolver(records)
    _install_refresh_edges(monkeypatch, resolver=resolver)
    query, _writes = _query_factory(token_rows=[{"api_token": "enc:token"}])
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=True, current_user=_owner()
    )

    assert result["dkim"]["valid"] is False
    assert result["dkim"]["error"].endswith("mandrill, s1, s2")
    assert result["reputation_score"] == 80


@pytest.mark.asyncio
async def test_a_broken_stored_token_is_ignored_without_failing_the_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def decrypt(_value: str, **_kwargs: Any) -> str:
        raise ValueError("undecryptable")

    monkeypatch.setattr(domain_shield, "decrypt_secret", decrypt)
    resolver = _FakeResolver(_full_records())
    _install_refresh_edges(monkeypatch, resolver=resolver)
    query, _writes = _query_factory(token_rows=[{"api_token": "enc:token"}])
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=True, current_user=_owner()
    )

    assert result["dkim"]["valid"] is True
    assert result["reputation_score"] == 100


@pytest.mark.asyncio
async def test_an_empty_stored_token_skips_cloudflare_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def decrypt(_value: str, **_kwargs: Any) -> str:
        raise AssertionError("must not decrypt an empty token")

    monkeypatch.setattr(domain_shield, "decrypt_secret", decrypt)
    resolver = _FakeResolver(_full_records())
    _install_refresh_edges(monkeypatch, resolver=resolver)
    query, _writes = _query_factory(token_rows=[{"api_token": ""}])
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=True, current_user=_owner()
    )

    assert result["reputation_score"] == 100


@pytest.mark.asyncio
async def test_a_blacklist_listing_lowers_the_refreshed_score_with_a_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = _FakeResolver({})
    _install_refresh_edges(
        monkeypatch,
        resolver=resolver,
        ssl_days=-1,
        blacklists=(["Spamhaus DBL", "SURBL List"], []),
    )
    query, _writes = _query_factory()
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=True, current_user=_owner()
    )

    assert result["reputation_score"] == 30
    assert result["score_grade"] == "F"
    assert result["blacklists"] == {
        "listed": True,
        "matched": ["Spamhaus DBL", "SURBL List"],
        "error": None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dmarc_txt", "expected_score", "expected_grade"),
    [
        # Missing SPF costs 20; the DMARC record then costs 10 or 20 more.
        ("v=DMARC1; p=quarantine", 70, "C"),
        ("v=DMARC1; p=none", 60, "D"),
    ],
)
async def test_the_refreshed_grade_follows_the_score_bands(
    monkeypatch: pytest.MonkeyPatch,
    dmarc_txt: str,
    expected_score: int,
    expected_grade: str,
) -> None:
    records = _full_records()
    records[(f"_dmarc.{DOMAIN}", "TXT")] = [_TxtAnswer(dmarc_txt.encode())]
    del records[(DOMAIN, "TXT")]
    resolver = _FakeResolver(records)
    _install_refresh_edges(monkeypatch, resolver=resolver)
    query, _writes = _query_factory()
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=True, current_user=_owner()
    )

    assert result["reputation_score"] == expected_score
    assert result["score_grade"] == expected_grade


@pytest.mark.asyncio
async def test_an_unchanged_posture_leaves_the_history_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = _FakeResolver(_full_records())
    _install_refresh_edges(monkeypatch, resolver=resolver, ssl_days=42)
    current = {
        "reputation_score": 100,
        "score_grade": "A",
        "spf_valid": 1,
        "dkim_valid": 1,
        "dmarc_valid": 1,
        "ssl_valid": 1,
    }
    query, writes = _query_factory(history_rows=[current])
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=True, current_user=_owner()
    )

    assert result["reputation_score"] == 100
    assert _tables(writes) == ["INSERT INTO app_domain_shield_status"]


@pytest.mark.asyncio
async def test_an_improved_posture_opens_a_new_history_row_without_an_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = _FakeResolver(_full_records())
    _install_refresh_edges(monkeypatch, resolver=resolver, ssl_days=42)
    previous = {
        "reputation_score": 80,
        "score_grade": "B",
        "spf_valid": 0,
        "dkim_valid": 1,
        "dmarc_valid": 1,
        "ssl_valid": 1,
    }
    query, writes = _query_factory(history_rows=[previous])
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    await domain_shield.check_domain_shield_status(DOMAIN, refresh=True, current_user=_owner())

    tables = _tables(writes)
    assert tables == [
        "UPDATE app_domain_shield_history",
        "INSERT INTO app_domain_shield_history",
        "INSERT INTO app_domain_shield_status",
    ]
    assert writes[0][1][1:] == ("workspace-1", DOMAIN)


@pytest.mark.asyncio
async def test_a_degraded_posture_records_an_alert_and_emails_the_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Score fell from 100 to 35: the alert row is written and Loops is called."""
    resolver = _FakeResolver({})
    _install_refresh_edges(monkeypatch, resolver=resolver, ssl_days=-1)
    previous = {
        "reputation_score": 100,
        "score_grade": "A",
        "spf_valid": 1,
        "dkim_valid": 1,
        "dmarc_valid": 1,
        "ssl_valid": 1,
    }
    preference = {"email_enabled": 1, "notify_domain_shield": 1}
    query, writes = _query_factory(history_rows=[previous], preference_rows=[preference])
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)

    policy_calls: list[tuple[Any, str]] = []

    def allowed(pref: dict[str, Any] | None, now: datetime, event_type: str) -> bool:
        policy_calls.append((pref, event_type))
        assert now.tzinfo is not None
        return True

    monkeypatch.setattr(domain_shield, "notification_is_allowed", allowed)

    sent: list[dict[str, Any]] = []

    async def send(**kwargs: Any) -> bool:
        sent.append(kwargs)
        return True

    monkeypatch.setattr("core.loops.send_loops_transactional", send)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=True, current_user=_owner()
    )

    assert result["reputation_score"] == 35
    assert policy_calls == [(preference, "domain_shield")]

    alert_sql, alert_params = writes[0]
    assert alert_sql.startswith("INSERT INTO app_alert_history")
    assert "'domain_shield', 'domain-shield'" in alert_sql
    assert alert_params[1:4] == ("workspace-1", DOMAIN, "Protection du domaine dégradée")
    assert alert_params[4] == f"Le score de {DOMAIN} est passé de 100 à 35."
    assert alert_params[5].endswith("Z")

    assert len(sent) == 1
    assert sent[0]["email"] == "owner@example.test"
    assert sent[0]["transactional_id"] == "tx-dns-shield"
    variables = sent[0]["data_variables"]
    assert set(variables) == {"firstName", "domainName", "dnsAnomalyDetails", "domainShieldUrl"}
    assert variables["firstName"] == "Owner"
    assert variables["domainName"] == DOMAIN
    assert variables["domainShieldUrl"] == "https://app.sicurre.test/"
    assert variables["dnsAnomalyDetails"].splitlines() == [
        "- SPF manquant ou invalide",
        "- Signature DKIM absente ou non alignée",
        "- Politique DMARC absente (vulnérabilité critique d'usurpation)",
    ]

    tables = _tables(writes)
    assert tables == [
        "INSERT INTO app_alert_history",
        "UPDATE app_domain_shield_history",
        "INSERT INTO app_domain_shield_history",
        "INSERT INTO app_domain_shield_status",
    ]


@pytest.mark.asyncio
async def test_a_muted_preference_records_the_alert_but_sends_no_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the reporting address is missing: the generic anomaly line is prepared."""
    records = _full_records()
    records[(f"_dmarc.{DOMAIN}", "TXT")] = [_TxtAnswer(b"v=DMARC1; p=reject")]
    resolver = _FakeResolver(records)
    _install_refresh_edges(monkeypatch, resolver=resolver, ssl_days=10)
    previous = {
        "reputation_score": 100,
        "score_grade": "A",
        "spf_valid": 1,
        "dkim_valid": 1,
        "dmarc_valid": 1,
        "ssl_valid": 1,
    }
    query, writes = _query_factory(history_rows=[previous])
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)
    monkeypatch.setattr(domain_shield, "notification_is_allowed", lambda *_args: False)

    async def send(**_kwargs: Any) -> bool:
        raise AssertionError("Loops must not be called when the preference mutes it")

    monkeypatch.setattr("core.loops.send_loops_transactional", send)

    result = await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=True, current_user=_nameless_owner()
    )

    assert result["reputation_score"] == 90
    assert result["score_grade"] == "A"
    assert writes[0][0].startswith("INSERT INTO app_alert_history")
    assert writes[0][1][4] == f"Le score de {DOMAIN} est passé de 100 à 90."
    # Same grade and same validity flags, but a different score: still a change.
    tables = _tables(writes)
    assert tables[1:] == [
        "UPDATE app_domain_shield_history",
        "INSERT INTO app_domain_shield_history",
        "INSERT INTO app_domain_shield_status",
    ]


@pytest.mark.asyncio
async def test_a_nameless_owner_is_greeted_generically_with_the_default_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def settings_without_url() -> SimpleNamespace:
        settings = _settings()
        settings.public_api_url = None
        return settings

    records = _full_records()
    records[(f"_dmarc.{DOMAIN}", "TXT")] = [_TxtAnswer(b"v=DMARC1; p=reject")]
    resolver = _FakeResolver(records)
    _install_refresh_edges(monkeypatch, resolver=resolver)
    monkeypatch.setattr(domain_shield, "get_settings", settings_without_url)
    previous = {
        "reputation_score": 100,
        "score_grade": "A",
        "spf_valid": 1,
        "dkim_valid": 1,
        "dmarc_valid": 1,
        "ssl_valid": 1,
    }
    query, _writes = _query_factory(history_rows=[previous])
    monkeypatch.setattr(domain_shield, "execute_runtime_query", query)
    monkeypatch.setattr(workspace_scope, "execute_runtime_query", query)
    monkeypatch.setattr(domain_shield, "notification_is_allowed", lambda *_args: True)

    sent: list[dict[str, Any]] = []

    async def send(**kwargs: Any) -> bool:
        sent.append(kwargs)
        return True

    monkeypatch.setattr("core.loops.send_loops_transactional", send)

    await domain_shield.check_domain_shield_status(
        DOMAIN, refresh=True, current_user=_nameless_owner()
    )

    assert sent[0]["data_variables"] == {
        "firstName": "Utilisateur",
        "domainName": DOMAIN,
        "dnsAnomalyDetails": "- Détérioration globale des métriques DNS",
        "domainShieldUrl": "http://localhost:5173/",
    }
