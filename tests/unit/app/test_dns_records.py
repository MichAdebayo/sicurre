"""Record helpers: the branches the route tests never reach."""

from __future__ import annotations

from data_platform.services.dns_records import (
    clean_str,
    has_usable_dkim,
    merge_dmarc,
    merge_spf,
    withdraw_dmarc_reporting,
)


def test_clean_str_unwraps_a_bytes_repr_and_tolerates_nothing() -> None:
    assert clean_str("b'v=spf1 -all'") == "v=spf1 -all"
    assert clean_str('b"v=spf1 -all"') == "v=spf1 -all"
    assert clean_str("") == ""
    assert clean_str("  v=spf1 -all ") == "v=spf1 -all"


def test_merge_spf_keeps_one_copy_of_a_repeated_mechanism() -> None:
    merged = merge_spf("v=spf1 include:_spf.google.com include:_spf.google.com -all")
    assert merged == "v=spf1 include:_spf.google.com include:_spf.mx.cloudflare.net -all"


def test_a_record_that_is_not_dkim_is_never_a_usable_key() -> None:
    assert has_usable_dkim("v=spf1 -all") is False
    assert has_usable_dkim("v=DKIM1; k=rsa; p=") is False
    assert has_usable_dkim("v=DKIM1; k=rsa; p=" + "A" * 100) is True


def test_merge_dmarc_lifts_a_monitor_only_policy_to_quarantine() -> None:
    assert merge_dmarc("v=DMARC1; p=none") == (
        "v=DMARC1; p=quarantine; rua=mailto:dmarc@sicurre.com"
    )


def test_withdrawal_drops_the_empty_tag_left_by_a_trailing_separator() -> None:
    record = "v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com;"
    assert withdraw_dmarc_reporting(record) == "v=DMARC1; p=reject"
