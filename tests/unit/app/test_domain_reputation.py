"""Domain reputation response classification tests."""

from collections.abc import Callable

import pytest

from data_platform.api.routers import app_routes
from data_platform.api.routers.app_routes import (
    _check_domain_blacklists,
    _classify_blocklist_response,
)


def test_spamhaus_resolver_error_is_not_a_listing() -> None:
    """Spamhaus access errors must not reduce a customer's security score."""
    listed, error = _classify_blocklist_response("Spamhaus DBL", ["127.255.255.254"])

    assert listed is False
    assert error is not None


def test_spamhaus_dbl_result_is_a_listing() -> None:
    """A documented DBL response remains a real positive result."""
    listed, error = _classify_blocklist_response("Spamhaus DBL", ["127.0.1.4"])

    assert listed is True
    assert error is None


def test_surbl_blocked_response_is_not_a_listing() -> None:
    """SURBL's blocked-access code is an availability warning, not a listing."""
    listed, error = _classify_blocklist_response("SURBL List", ["127.0.0.1"])

    assert listed is False
    assert error is not None


def test_surbl_bitmask_result_is_a_listing() -> None:
    """A valid SURBL bitmask response remains a positive result."""
    listed, error = _classify_blocklist_response("SURBL List", ["127.0.0.126"])

    assert listed is True
    assert error is None


def test_invalid_and_unknown_responses_are_ignored() -> None:
    """Malformed addresses and unknown providers cannot create a false listing."""
    listed, error = _classify_blocklist_response("Unknown", ["not-an-address"])

    assert listed is False
    assert error is None


@pytest.mark.asyncio
async def test_blocklist_check_separates_listings_and_access_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider errors remain separate from genuine positive results."""

    async def direct_call(function: Callable[..., object], *args: object) -> object:
        return function(*args)

    def resolve(hostname: str, _record_type: str) -> list[str]:
        if hostname.endswith("dbl.spamhaus.org"):
            return ["127.255.255.254"]
        return ["127.0.0.126"]

    monkeypatch.setattr(app_routes.asyncio, "to_thread", direct_call)
    monkeypatch.setattr("dns.resolver.resolve", resolve)

    listed, unavailable = await _check_domain_blacklists("vinse.app")

    assert listed == ["SURBL List"]
    assert unavailable == ["Spamhaus indisponible depuis le résolveur du serveur"]


@pytest.mark.asyncio
async def test_blocklist_resolution_failures_are_not_listings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NXDOMAIN and transport failures are treated as negative, not unsafe."""

    async def direct_call(function: Callable[..., object], *args: object) -> object:
        return function(*args)

    def unavailable(_hostname: str, _record_type: str) -> list[str]:
        raise RuntimeError("resolver unavailable")

    monkeypatch.setattr(app_routes.asyncio, "to_thread", direct_call)
    monkeypatch.setattr("dns.resolver.resolve", unavailable)

    assert await _check_domain_blacklists("vinse.app") == ([], [])
