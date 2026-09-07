"""Reading a customer's zone must not mistake one record for another.

The apex of a real zone carries SPF beside Google and Microsoft verification
tokens. Treating any apex TXT as SPF read a token as the customer's SPF record,
and `_merge_spf` then saw no `v=spf1` prefix and returned a fresh default -
silently discarding the record their mail provider depends on.
"""

from __future__ import annotations

from data_platform.api.routers.integrations import _merge_spf, _read_dns_state

GOOGLE = {"type": "TXT", "name": "example.test", "content": "google-site-verification=Kx9wQ2mPl0"}
MICROSOFT = {"type": "TXT", "name": "example.test", "content": "MS=ms84720193"}
SPF = {"type": "TXT", "name": "example.test", "content": "v=spf1 include:mail.example.net -all"}
DMARC = {"type": "TXT", "name": "_dmarc.example.test", "content": "v=DMARC1; p=reject"}
DKIM = {"type": "TXT", "name": "cf2024-1._domainkey.example.test",
        "content": "v=DKIM1; h=sha256; k=rsa; p=" + "MIIBIjANBgkqhkiG9w0BAQEF" * 17}
MX = {"type": "MX", "name": "example.test", "content": "route1.mx.cloudflare.net"}


def test_spf_is_found_among_verification_tokens() -> None:
    """Order must not decide which record is read as SPF."""
    for records in (
        [GOOGLE, MICROSOFT, SPF],
        [SPF, GOOGLE, MICROSOFT],
        [GOOGLE, SPF, MICROSOFT],
    ):
        spf, _, _ = _read_dns_state(records, "example.test")
        assert spf == SPF["content"], f"order {[r['content'][:12] for r in records]}"


def test_a_verification_token_is_never_read_as_spf() -> None:
    """With no SPF present the result is empty, not a token."""
    spf, _, _ = _read_dns_state([GOOGLE, MICROSOFT], "example.test")
    assert spf == ""


def test_a_zone_without_spf_gets_one_created_not_a_token_rewritten() -> None:
    """The end-to-end consequence: the customer's tokens survive."""
    spf, _, _ = _read_dns_state([GOOGLE, MICROSOFT], "example.test")
    merged = _merge_spf(spf)
    assert merged.startswith("v=spf1")
    assert "google-site-verification" not in merged
    assert "MS=" not in merged


def test_an_existing_spf_is_preserved_and_extended() -> None:
    """The customer's own includes must survive the merge."""
    spf, _, _ = _read_dns_state([GOOGLE, SPF], "example.test")
    merged = _merge_spf(spf)
    assert "include:mail.example.net" in merged, "the customer's mail provider was dropped"
    assert merged.endswith("-all"), "their strict policy was weakened"


def test_dmarc_and_dkim_are_read_from_their_own_names() -> None:
    spf, dkim, dmarc = _read_dns_state([GOOGLE, SPF, DMARC, DKIM, MX], "example.test")
    assert spf == SPF["content"]
    assert dmarc == DMARC["content"]
    assert dkim == DKIM["content"]


def test_non_txt_records_are_ignored() -> None:
    """An MX record at the apex must never be mistaken for SPF."""
    spf, _, _ = _read_dns_state([MX], "example.test")
    assert spf == ""


def test_quoted_and_trailing_dot_forms_are_handled() -> None:
    """Providers return quoted values and fully qualified names."""
    spf, _, dmarc = _read_dns_state(
        [
            {"type": "TXT", "name": "Example.Test.", "content": '"v=spf1 -all"'},
            {"type": "TXT", "name": "_dmarc.Example.Test.", "content": '"v=DMARC1; p=reject"'},
        ],
        "example.test",
    )
    assert spf == "v=spf1 -all"
    assert dmarc == "v=DMARC1; p=reject"


# --------------------------------------------------------------------------- ──
# DKIM is observed, never authored. The signing key belongs to whoever sends the
# mail, so Sicurre publishing one produced a record no verifier could use, at a
# selector nothing reads, which its own check then accepted as proof.
# --------------------------------------------------------------------------- ──

PLACEHOLDER = {
    "type": "TXT", "name": "cloudflare._domainkey.example.test",
    "content": "v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...",
}
REAL_CF = {
    "type": "TXT", "name": "cf2024-1._domainkey.example.test",
    "content": "v=DKIM1; h=sha256; k=rsa; p=" + "MIIBIjANBgkqhkiG9w0BAQEF" * 17,
}
REVOKED = {"type": "TXT", "name": "cf2024-1._domainkey.example.test", "content": "v=DKIM1; k=rsa; p="}


def test_a_placeholder_key_is_not_accepted_as_dkim() -> None:
    """The stub Sicurre used to publish must not certify itself."""
    _, dkim, _ = _read_dns_state([PLACEHOLDER], "example.test")
    assert dkim == ""


def test_a_real_key_is_accepted_whatever_the_selector() -> None:
    """Cloudflare, Google and Microsoft all use different selectors."""
    for name in (
        "cf2024-1._domainkey.example.test",
        "google._domainkey.example.test",
        "selector1._domainkey.example.test",
    ):
        _, dkim, _ = _read_dns_state([{**REAL_CF, "name": name}], "example.test")
        assert dkim, f"a genuine key at {name} must count"


def test_a_revoked_key_is_not_configured_dkim() -> None:
    """An empty p= revokes the key; it is not a working signature."""
    _, dkim, _ = _read_dns_state([REVOKED], "example.test")
    assert dkim == ""


def test_a_real_key_wins_over_a_placeholder_on_the_same_zone() -> None:
    """vinse.app carries both today: the stub must not mask the real one."""
    for records in ([PLACEHOLDER, REAL_CF], [REAL_CF, PLACEHOLDER]):
        _, dkim, _ = _read_dns_state(records, "example.test")
        assert dkim == REAL_CF["content"]


def test_domain_shield_never_writes_a_dkim_record() -> None:
    """No code path may publish a signing key Sicurre does not hold."""
    import inspect

    from data_platform.api.routers import integrations

    source = inspect.getsource(integrations)
    assert "_domainkey.{" not in source, "a DKIM record name is built for writing"
    # An assignment, not a mention: the docstrings describe the old bug on purpose.
    assert 'dkim_rec = "v=DKIM1' not in source, "a DKIM record value is authored here"
    assert "fix_dkim" not in source, "the DKIM fix flag should be gone"
    # The read path may still name the selector; that is observation, not authorship.
    assert "_domainkey." in source, "detection must still recognise DKIM selectors"


# --------------------------------------------------------------------------- ──
# SPF is a record on someone else's domain, with a ten DNS lookup budget and a
# policy that decides whether their mail is rejected. Sicurre may add what
# Email Routing needs and withdraw what it wrongly added before; everything
# else in there belongs to the customer.
# --------------------------------------------------------------------------- ──

CF = "include:_spf.mx.cloudflare.net"


def test_a_missing_record_gets_the_routing_include_and_softfail() -> None:
    """`-all` on a record we invented would reject senders we cannot see."""
    assert _merge_spf("") == f"v=spf1 {CF} ~all"


def test_the_dead_include_is_withdrawn() -> None:
    """spf.cloudflare.com publishes no SPF record; RFC 7208 calls that permerror."""
    merged = _merge_spf("v=spf1 include:spf.cloudflare.com ~all")
    assert "spf.cloudflare.com" not in merged
    assert CF in merged


def test_the_self_authorisation_is_withdrawn() -> None:
    """Sicurre never sends as the customer, so it does not hold a permit to."""
    merged = _merge_spf("v=spf1 include:sicurre.com ~all")
    assert "include:sicurre.com" not in merged


def test_the_customers_own_mechanisms_survive() -> None:
    """Dropping one of these silently stops their real mail."""
    merged = _merge_spf(
        "v=spf1 include:_spf.google.com include:servers.mcsv.net ip4:198.51.100.7 "
        "include:spf.cloudflare.com -all"
    )
    for kept in ("include:_spf.google.com", "include:servers.mcsv.net", "ip4:198.51.100.7"):
        assert kept in merged, f"{kept} was dropped from the customer's record"
    assert "spf.cloudflare.com" not in merged


def test_an_existing_policy_is_never_loosened_or_tightened() -> None:
    """The all mechanism is the customer's decision, not ours."""
    assert _merge_spf("v=spf1 ip4:198.51.100.7 -all").endswith("-all")
    assert _merge_spf("v=spf1 ip4:198.51.100.7 ~all").endswith("~all")
    assert _merge_spf("v=spf1 ip4:198.51.100.7 ?all").endswith("?all")


def test_the_routing_include_is_not_duplicated() -> None:
    """Repeated syncs must not grow the record or its lookup count."""
    once = _merge_spf(f"v=spf1 {CF} ~all")
    assert once.count(CF) == 1
    assert _merge_spf(once) == once, "merging is not idempotent"


def test_a_non_spf_value_is_never_extended() -> None:
    """A verification token reaching this function must not become an SPF record."""
    assert _merge_spf("google-site-verification=Kx9wQ2mPl0") == f"v=spf1 {CF} ~all"
