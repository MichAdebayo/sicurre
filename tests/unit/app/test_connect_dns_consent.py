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

from data_platform.api.routers import integrations
from data_platform.api.routers.integrations import (
    CloudflareSetupRequest,
    _merge_dmarc,
    _merge_spf,
    _planned_change,
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
