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


def test_spamhaus_dqs_misconfiguration_is_not_a_listing() -> None:
    """DQS 'typo in DNSBL name' error must not reduce a customer's score."""
    listed, error = _classify_blocklist_response("Spamhaus DBL", ["127.255.255.252"])

    assert listed is False
    assert error is not None


def test_spamhaus_excessive_queries_is_not_a_listing() -> None:
    """DQS 'excessive queries' error must not reduce a customer's score."""
    listed, error = _classify_blocklist_response("Spamhaus DBL", ["127.255.255.255"])

    assert listed is False
    assert error is not None


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


@pytest.mark.asyncio
async def test_dqs_key_routes_spamhaus_through_authenticated_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a DQS key is provided, Spamhaus queries use dbl.dq.spamhaus.net."""

    queried_hosts: list[str] = []

    async def direct_call(function: Callable[..., object], *args: object) -> object:
        return function(*args)

    def resolve(hostname: str, _record_type: str) -> list[str]:
        queried_hosts.append(hostname)
        if hostname.endswith("dbl.dq.spamhaus.net"):
            # Clean domain on DQS
            raise RuntimeError("NXDOMAIN")
        if hostname.endswith("multi.surbl.org"):
            raise RuntimeError("NXDOMAIN")
        return []

    monkeypatch.setattr(app_routes.asyncio, "to_thread", direct_call)
    monkeypatch.setattr("dns.resolver.resolve", resolve)

    await _check_domain_blacklists("example.com", dqs_key="synthetic-fixture")

    # Spamhaus query should go through DQS endpoint, not free mirror
    spamhaus_queries = [h for h in queried_hosts if "spamhaus" in h]
    assert len(spamhaus_queries) == 1
    assert spamhaus_queries[0] == "example.com.synthetic-fixture.dbl.dq.spamhaus.net"
    # SURBL should still use multi.surbl.org
    surbl_queries = [h for h in queried_hosts if "surbl" in h]
    assert len(surbl_queries) == 1
    assert surbl_queries[0] == "example.com.multi.surbl.org"


@pytest.mark.asyncio
async def test_without_dqs_key_uses_free_spamhaus_mirror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a DQS key, Spamhaus queries use the free public mirror."""

    queried_hosts: list[str] = []

    async def direct_call(function: Callable[..., object], *args: object) -> object:
        return function(*args)

    def resolve(hostname: str, _record_type: str) -> list[str]:
        queried_hosts.append(hostname)
        raise RuntimeError("NXDOMAIN")

    monkeypatch.setattr(app_routes.asyncio, "to_thread", direct_call)
    monkeypatch.setattr("dns.resolver.resolve", resolve)

    await _check_domain_blacklists("example.com")

    spamhaus_queries = [h for h in queried_hosts if "spamhaus" in h]
    assert len(spamhaus_queries) == 1
    assert spamhaus_queries[0] == "example.com.dbl.spamhaus.org"
