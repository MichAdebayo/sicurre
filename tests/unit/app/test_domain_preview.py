"""The onboarding preview reads public DNS and never needs a token."""

from __future__ import annotations

import inspect

import pytest

from core.domain_preview import normalize_zone, read_public_dns, read_public_dns_sync
from data_platform.api.auth import AuthUser
from data_platform.api.routers import integrations


def _resolver(records: dict[tuple[str, str], list[str]]):
    def resolve(name: str, rrtype: str) -> list[str]:
        try:
            return records[(name, rrtype)]
        except KeyError as exc:
            raise LookupError(name) from exc

    return resolve


def _handler():
    """The route body without the rate-limit wrapper, which needs a live request."""
    return getattr(integrations.preview_cloudflare_domain, "__wrapped__", integrations.preview_cloudflare_domain)


def _user() -> AuthUser:
    return AuthUser(
        id="user-1",
        email="owner@example.test",
        display_name="Owner",
        role="owner",
        workspace_id="workspace-1",
        workspace_name="Example",
        is_platform_admin=False,
    )


def test_zone_names_are_normalised_and_junk_is_refused() -> None:
    assert normalize_zone("  Sicurre.COM. ") == "sicurre.com"
    assert normalize_zone("not a domain") is None
    assert normalize_zone("javascript:alert(1)") is None


def test_a_cloudflare_zone_with_another_mail_provider_is_described_as_such() -> None:
    snapshot = read_public_dns_sync(
        "example.test",
        _resolver(
            {
                ("example.test", "NS"): ["ada.ns.cloudflare.com", "bob.ns.cloudflare.com"],
                ("example.test", "MX"): ["aspmx.l.google.com"],
                ("example.test", "TXT"): ["google-site-verification=abc", "v=spf1 include:_spf.google.com ~all"],
                ("_dmarc.example.test", "TXT"): ["v=DMARC1; p=none"],
                ("google._domainkey.example.test", "TXT"): ["v=DKIM1; k=rsa; p=MIIB"],
            }
        ),
    )
    assert snapshot.resolvable and snapshot.on_cloudflare
    assert snapshot.mail_provider == "other"
    assert snapshot.spf == "v=spf1 include:_spf.google.com ~all"
    assert snapshot.dmarc == "v=DMARC1; p=none"
    assert snapshot.dkim_present is True


def test_cloudflare_routing_and_an_empty_zone_read_cleanly() -> None:
    routed = read_public_dns_sync(
        "routed.test",
        _resolver({("routed.test", "NS"): ["x.ns.cloudflare.com"], ("routed.test", "MX"): ["route1.mx.cloudflare.net"]}),
    )
    assert routed.mail_provider == "cloudflare" and routed.spf == "" and routed.dmarc == ""
    nowhere = read_public_dns_sync("elsewhere.test", _resolver({("elsewhere.test", "NS"): ["ns1.ovh.net"]}))
    assert nowhere.on_cloudflare is False and nowhere.mail_provider == "none"


def test_an_unknown_domain_is_unresolvable_and_nothing_else_is_looked_up() -> None:
    calls: list[tuple[str, str]] = []

    def resolve(name: str, rrtype: str) -> list[str]:
        calls.append((name, rrtype))
        raise LookupError(name)

    snapshot = read_public_dns_sync("nope.invalid", resolve)
    assert snapshot.resolvable is False
    assert calls == [("nope.invalid", "NS")]


def test_the_preview_route_needs_no_token_and_never_touches_cloudflare() -> None:
    assert "cf_api_token" not in inspect.signature(integrations.DomainPreviewRequest).parameters
    assert not hasattr(integrations.DomainPreviewRequest.model_fields.get("cf_api_token"), "annotation")
    source = inspect.getsource(integrations.preview_cloudflare_domain)
    assert "CloudflareProvisioner" not in source
    assert "deploy_dns_record" not in source


@pytest.mark.asyncio
async def test_the_preview_route_reports_the_plan_from_public_dns(monkeypatch) -> None:
    async def fake_read(zone: str, resolve=None):
        assert zone == "sicurre.com"
        return await read_public_dns(
            zone,
            _resolver(
                {
                    ("sicurre.com", "NS"): ["ada.ns.cloudflare.com"],
                    ("sicurre.com", "MX"): ["route1.mx.cloudflare.net"],
                    ("sicurre.com", "TXT"): ["v=spf1 include:_spf.google.com ~all"],
                    ("_dmarc.sicurre.com", "TXT"): ["v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com"],
                }
            ),
        )

    monkeypatch.setattr(integrations, "read_public_dns", fake_read)
    result = await _handler()(
        integrations.DomainPreviewRequest(zone_name="Sicurre.com"), request=None, current_user=_user()
    )
    assert result["on_cloudflare"] is True
    assert result["mail_provider"] == "cloudflare"
    assert result["plan"] == {"spf": "modify", "dmarc": "keep", "dkim_present": False}
    assert result["dmarc_policy"] == "reject" and result["dmarc_reporting"] is True


@pytest.mark.asyncio
async def test_an_unresolvable_domain_is_reported_not_raised(monkeypatch) -> None:
    async def fake_read(zone: str, resolve=None):
        return await read_public_dns(zone, _resolver({}))

    monkeypatch.setattr(integrations, "read_public_dns", fake_read)
    result = await _handler()(
        integrations.DomainPreviewRequest(zone_name="nope.invalid"), request=None, current_user=_user()
    )
    assert result == {"zone_name": "nope.invalid", "resolvable": False, "on_cloudflare": False, "mail_provider": "none"}


@pytest.mark.asyncio
async def test_a_value_that_is_not_a_hostname_is_refused_with_422() -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        await _handler()(
            integrations.DomainPreviewRequest(zone_name="not a domain"), request=None, current_user=_user()
        )
    assert excinfo.value.status_code == 422


def test_the_default_resolver_reads_txt_mx_and_ns_answers(monkeypatch) -> None:
    """The dnspython adapter joins TXT chunks, keeps MX exchanges, strips trailing dots."""
    import sys
    import types

    from core import domain_preview

    class Txt:
        strings = (b"v=spf1 ", b"include:_spf.google.com ~all")

    class Mx:
        exchange = "aspmx.l.google.com."

    class Ns:
        def __str__(self) -> str:
            return "ada.ns.cloudflare.com."

    answers = {"TXT": [Txt()], "MX": [Mx()], "NS": [Ns()]}
    fake = types.SimpleNamespace(resolve=lambda name, rrtype: answers[rrtype])
    monkeypatch.setitem(sys.modules, "dns.resolver", fake)

    assert domain_preview._default_resolver("example.test", "TXT") == ["v=spf1 include:_spf.google.com ~all"]
    assert domain_preview._default_resolver("example.test", "MX") == ["aspmx.l.google.com"]
    assert domain_preview._default_resolver("example.test", "NS") == ["ada.ns.cloudflare.com"]
