"""Decode RFC 2047 headers and extract MIME bodies."""

from __future__ import annotations

import binascii
import re
from email import message_from_string
from email.errors import HeaderParseError
from email.header import decode_header, make_header
from html import unescape


def decode_mime_header(value: str | None) -> str:
    """Return the readable form of a possibly encoded-word header."""
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


def extract_mime_body(value: str | None) -> str:
    """Return the human-readable body of a raw MIME message."""
    if not value:
        return ""
    # A body without headers has no colon-terminated header block to strip.
    if "\n" not in value or not _looks_like_mime(value):
        return value
    try:
        message = message_from_string(value)
    except (ValueError, TypeError):
        return value

    html_fallback = ""
    for part in message.walk() if message.is_multipart() else [message]:
        if part.get_content_maintype() == "multipart":
            continue
        content_type = part.get_content_type()
        if content_type not in ("text/plain", "text/html"):
            continue
        try:
            payload = part.get_payload(decode=True)
        except (AssertionError, binascii.Error, ValueError):
            continue
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="replace")
        except (LookupError, UnicodeDecodeError):
            text = payload.decode("utf-8", errors="replace")
        if content_type == "text/plain" and text.strip():
            return text.strip()
        if content_type == "text/html" and not html_fallback:
            html_fallback = text

    if html_fallback:
        return _strip_html(html_fallback).strip()
    # Parsed as MIME but carried no text part: return the payload rather than
    # the headers, so the caller never sees a routing block as the body.
    body = message.get_payload()
    return body.strip() if isinstance(body, str) and body.strip() else value


def _looks_like_mime(value: str) -> bool:
    """True when the string opens with a header block rather than prose."""
    head = value.lstrip()[:2000]
    return bool(re.match(r"^[A-Za-z-]+:\s", head)) and any(
        marker in head
        for marker in ("Received:", "Content-Type:", "MIME-Version:", "From:", "Date:")
    )


def _strip_html(value: str) -> str:
    without_blocks = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", value)
    return unescape(re.sub(r"(?s)<[^>]+>", " ", without_blocks))
