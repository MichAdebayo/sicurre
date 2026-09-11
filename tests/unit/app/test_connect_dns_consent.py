"""Connecting a domain must not rewrite records nobody was shown.

The Connect button sent no `fix_spf` or `fix_dmarc`, and both defaulted to
true, so connecting silently rewrote a customer's SPF and DMARC before they had
seen either record. By the time Domain Shield offered them a checkbox, the
write had already happened — the consent was theatre.

The defaults are off, so a caller that says nothing changes nothing. The
interface now reads the zone first, shows what would change, and sends the
answer explicitly.
"""

from __future__ import annotations

import inspect

import pytest

from data_platform.api.auth import AuthUser
from data_platform.api.routers import integrations
from data_platform.api.routers.integrations import (
    CloudflareSetupRequest,
    _merge_dmarc,
    _merge_spf,
    _planned_change,
)


def _user() -> AuthUser:
    return AuthUser(
        id="user-1",
        email="owner@sicurre.com",
        display_name="Owner",
        role="owner",
        workspace_id="workspace-1",
        workspace_name="Workspace",
        is_platform_admin=False,
    )


def test_connecting_writes_nothing_unless_asked() -> None:
    """The regression: silence must mean "leave my DNS alone"."""
    request = CloudflareSetupRequest(
        zone_name="sicurre.com", destination_email="owner@sicurre.com"
    )
    assert request.fix_spf is False
    assert request.fix_dmarc is False


def test_consent_still_travels_when_it_is_given() -> None:
    request = CloudflareSetupRequest(
        zone_name="sicurre.com",
        destination_email="owner@sicurre.com",
        fix_spf=True,
        fix_dmarc=False,
    )
    assert request.fix_spf is True
    assert request.fix_dmarc is False


def test_a_missing_record_is_reported_as_an_addition() -> None:
    assert _planned_change("", _merge_spf("")) == "add"
    assert _planned_change("", _merge_dmarc("")) == "add"


def test_an_existing_record_that_changes_is_reported_as_a_modification() -> None:
    current = "v=spf1 include:_spf.google.com ~all"
    assert _planned_change(current, _merge_spf(current)) == "modify"


def test_a_record_already_correct_is_reported_as_unchanged() -> None:
    """Nothing to do must not be shown as a change the customer is consenting to."""
    settled = _merge_spf("v=spf1 include:_spf.google.com ~all")
    assert _planned_change(settled, _merge_spf(settled)) == "keep"

    dmarc = _merge_dmarc("v=DMARC1; p=reject; rua=mailto:owner@sicurre.com")
    assert _planned_change(dmarc, _merge_dmarc(dmarc)) == "keep"


def test_the_preview_is_computed_from_the_write_path() -> None:
    """A preview derived separately could promise something else.

    `_planned_change` compares the current record against the very merge the
    provisioner applies, so what the customer approves is what is written.
    """
    source = inspect.getsource(integrations.verify_cloudflare_token)
    assert "_merge_spf" in source
    assert "_merge_dmarc" in source
    assert "_read_dns_state" in source


def test_verifying_a_token_writes_nothing() -> None:
    """The preview reads the zone. It must never deploy while doing so."""
    source = inspect.getsource(integrations.verify_cloudflare_token)
    assert "deploy_dns_record" not in source, "the preview wrote to the zone"


@pytest.mark.asyncio
async def test_the_preview_reports_the_real_zone(monkeypatch) -> None:
    """Drive the endpoint: the plan must come from the customer's own records.

    A zone already carrying Google's SPF and a reject DMARC without our
    reporting address should be told SPF will be modified, DMARC modified, and
    DKIM is present — not a generic "we will change things".
    """
    dkim = "v=DKIM1; k=rsa; p=" + "MIIBIjANBgkqhkiG9w0BAQEF" * 17

    class Provisioner:
        def __init__(self, api_token: str) -> None:
            assert api_token == "token-abc"

        async def verify_token(self) -> bool:
            return True

        async def get_zone(self, zone_name: str) -> tuple[str, str]:
            assert zone_name == "sicurre.com"
            return "zone-1", "account-1"

        async def get_dns_records(self, zone_id: str) -> list[dict[str, str]]:
            assert zone_id == "zone-1"
            return [
                {"type": "TXT", "name": "sicurre.com",
                 "content": "v=spf1 include:_spf.google.com ~all"},
                {"type": "TXT", "name": "cf2024-1._domainkey.sicurre.com", "content": dkim},
                {"type": "TXT", "name": "_dmarc.sicurre.com",
                 "content": "v=DMARC1; p=reject"},
            ]

    monkeypatch.setattr(integrations, "CloudflareProvisioner", Provisioner)

    result = await integrations.verify_cloudflare_token(
        integrations.TokenVerifyRequest(cf_api_token="token-abc", zone_name="sicurre.com"),
        _user(),
    )

    assert result["valid"] is True
    assert result["plan"] == {"spf": "modify", "dmarc": "modify", "dkim_present": True}


@pytest.mark.asyncio
async def test_an_empty_zone_is_reported_as_additions(monkeypatch) -> None:
    """Nothing published yet means both records are added, not modified."""

    class Provisioner:
        def __init__(self, api_token: str) -> None:
            pass

        async def verify_token(self) -> bool:
            return True

        async def get_zone(self, _zone_name: str) -> tuple[str, str]:
            return "zone-1", "account-1"

        async def get_dns_records(self, _zone_id: str) -> list[dict[str, str]]:
            return []

    monkeypatch.setattr(integrations, "CloudflareProvisioner", Provisioner)

    result = await integrations.verify_cloudflare_token(
        integrations.TokenVerifyRequest(cf_api_token="t", zone_name="sicurre.com"),
        _user(),
    )

    assert result["plan"] == {"spf": "add", "dmarc": "add", "dkim_present": False}
