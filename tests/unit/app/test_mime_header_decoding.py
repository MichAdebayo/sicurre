"""Mail headers must be stored and shown as text, not as wire format.

Any non-ASCII header arrives RFC 2047 encoded, so a French subject reached the
database as `=?UTF-8?Q?...?=`. Three consequences, all live: the threat journal
and quarantine page displayed the encoding, the Loops alert quoted it back to
the customer, and the classifier scored the encoding rather than the words.

Headers are attacker-controlled, so decoding must never be able to fail a scan.
"""

from __future__ import annotations

import inspect

import pytest

from core.mime_headers import decode_mime_header
from data_platform.api.routers import integrations

#: The exact header observed in production on 4 September, split across two
#: encoded-words as mail clients do at the 75-character line limit.
_OBSERVED = (
    "=?UTF-8?Q?SICURRE=2DE2E=2D20260904=2D01_=E2=80=94_Your_account_will_be_sus?= "
    "=?UTF-8?Q?pended_within_24_hours?="
)


def test_the_observed_production_header_decodes_to_readable_text() -> None:
    decoded = decode_mime_header(_OBSERVED)
    assert decoded == "SICURRE-E2E-20260904-01 — Your account will be suspended within 24 hours"
    assert "=?" not in decoded


def test_multi_part_encoded_words_are_joined() -> None:
    """A long subject is split across encoded-words and must rejoin as one."""
    assert "suspended within" in decode_mime_header(_OBSERVED)


def test_plain_ascii_is_returned_untouched() -> None:
    assert decode_mime_header("Ordinary subject") == "Ordinary subject"


@pytest.mark.parametrize(
    "header",
    ["=?BAD?X?zz?=", "=?UTF-8?Q?", "=?=", "=?UTF-8?B?!!!notbase64!!!?="],
)
def test_a_malformed_header_returns_the_original_rather_than_raising(header: str) -> None:
    """A sender controls this string; a scan must not fail because it is broken."""
    assert decode_mime_header(header) == header


def test_empty_input_is_safe() -> None:
    assert decode_mime_header(None) == ""
    assert decode_mime_header("") == ""


def test_the_scan_decodes_before_anything_consumes_the_header() -> None:
    """Decoding after the rules or the classifier would leave them on wire format."""
    source = inspect.getsource(integrations)
    decode_at = source.index("payload.subject = decode_mime_header")
    for consumer in ("sender_lower = payload.sender.lower()", "db_subject = payload.subject"):
        assert decode_at < source.index(consumer), f"{consumer} runs before decoding"


def test_a_raw_mime_message_yields_only_the_body() -> None:
    """The Worker forwards the whole message; routing headers are not the mail."""
    from core.mime_headers import extract_mime_body

    raw = (
        "Received: from mail.example.net (10.0.0.1)\r\n"
        "        by cloudflare-email.net id ABC\r\n"
        "ARC-Seal: i=2; a=rsa-sha256; b=AAAA\r\n"
        "DKIM-Signature: v=1; a=rsa-sha256; b=BBBB\r\n"
        "From: attacker@example.net\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "Votre compte sera suspendu. Confirmez vos identifiants."
    )
    body = extract_mime_body(raw)
    assert body == "Votre compte sera suspendu. Confirmez vos identifiants."
    for header in ("ARC-Seal", "DKIM-Signature", "Received:"):
        assert header not in body


def test_plain_text_is_passed_through_untouched() -> None:
    """The POC and tests send a bare body with no headers."""
    from core.mime_headers import extract_mime_body

    assert extract_mime_body("Just a message body.") == "Just a message body."


def test_the_body_is_extracted_before_it_is_truncated() -> None:
    """Truncating first discarded the body: the headers alone exceed 4000 chars."""
    source = inspect.getsource(integrations)
    assert source.index("payload.text = extract_mime_body") < source.index(
        "anonymize_pii(payload.text)[:4000]"
    )
