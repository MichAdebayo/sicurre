"""Domain reputation response classification tests."""

from data_platform.api.routers.app_routes import _classify_blocklist_response


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
