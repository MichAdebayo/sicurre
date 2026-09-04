"""Decode RFC 2047 encoded-word headers into readable text.

Mail clients encode any non-ASCII header as an encoded-word, so a French
subject arrives as
`=?UTF-8?Q?SICURRE=2DE2E_=E2=80=94_Votre_compte?=` rather than as text. The
scan path stored that raw, so the threat journal, the quarantine page and the
Loops alert all showed the wire format instead of the subject, and the
classifier scored the encoding rather than the words.

`email.header` handles the parsing. What it does not do is fail safely: a
malformed header raises, and a header is attacker-controlled, so every failure
mode here returns the original string rather than propagating.
"""

from __future__ import annotations

import binascii
from email.errors import HeaderParseError
from email.header import decode_header, make_header


def decode_mime_header(value: str | None) -> str:
    """Return the readable form of a possibly encoded-word header.

    Plain ASCII passes through untouched. Anything that cannot be decoded is
    returned as it arrived: a mail header is attacker-controlled input, and a
    scan must not fail because a sender sent a malformed one.
    """
    if not value:
        return ""
    if "=?" not in value:
        # Not an encoded-word; avoid the parser entirely.
        return value
    try:
        decoded = str(make_header(decode_header(value)))
    except (
        HeaderParseError,   # malformed encoded-word structure
        binascii.Error,     # invalid base64 payload
        UnicodeDecodeError,
        LookupError,        # unknown charset
        ValueError,
        TypeError,
    ):
        return value
    # `make_header` can yield an empty string for input that was not empty;
    # keeping the original is more useful than losing the header.
    return decoded or value
