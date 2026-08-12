"""Derive privacy-safe context signals from an intercepted email."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from email import policy
from email.parser import Parser

_FORWARD_SUBJECT = re.compile(r"^\s*(?:fwd?|tr)\s*:", re.IGNORECASE)
_FORWARD_MARKER = re.compile(
    r"(?:-+\s*(?:forwarded message|message transféré)\s*-+|"
    r"début du message transféré|begin forwarded message)",
    re.IGNORECASE,
)
_SUBSCRIPTION_CLAIM = re.compile(
    r"(?:you (?:are|'re) receiving this(?: .{0,80})? because you subscribed|"
    r"vous recevez (?:cet|ce) .{0,80} parce que vous (?:êtes|etes) "
    r"(?:abonné|abonne|inscrit)|"
    r"confirmation d['’]inscription)",
    re.IGNORECASE | re.DOTALL,
)
_HEADER_BOUNDARY = re.compile(r"\r?\n\r?\n")
_AUTHENTICATION_RESULTS = re.compile(
    r"(?im)^authentication-results\s*:[^\r\n]*(?:\r?\n[ \t]+[^\r\n]*)*"
)
_CALENDAR_REQUIRED_LINES = (
    re.compile(r"(?im)^begin:vcalendar\s*$"),
    re.compile(r"(?im)^method\s*:\s*(?:request|reply|cancel)\s*$"),
    re.compile(r"(?im)^begin:vevent\s*$"),
    re.compile(r"(?im)^uid\s*:[^\r\n]+$"),
    re.compile(r"(?im)^dtstart(?:;[^:\r\n]+)?\s*:[^\r\n]+$"),
    re.compile(r"(?im)^end:vevent\s*$"),
    re.compile(r"(?im)^end:vcalendar\s*$"),
)


def _has_transactional_calendar(text: str) -> bool:
    """Recognize a coherent calendar MIME part without trusting prose claims."""

    try:
        message = Parser(policy=policy.default).parsestr(text[:10_000])
    except (TypeError, ValueError):
        return False
    for part in message.walk():
        if part.get_content_type() != "text/calendar":
            continue
        try:
            payload = part.get_content()
        except (KeyError, LookupError, UnicodeError, ValueError):
            continue
        if isinstance(payload, str) and all(
            pattern.search(payload) for pattern in _CALENDAR_REQUIRED_LINES
        ):
            return True
    return False


@dataclass(frozen=True, slots=True)
class EmailContextSignals:
    """Bounded evidence safe to send to the ML service."""

    structured_forward: bool
    outer_sender_authenticated: bool
    mailing_list_headers: bool
    subscription_claimed: bool
    recipient_expected: bool
    transactional_evidence: bool

    def as_payload(self) -> dict[str, bool]:
        """Return the stable service-to-service request shape."""

        return asdict(self)


def _header_block(text: str) -> str:
    """Return only the bounded RFC-822 header prefix when present."""

    prefix = text[:8_000]
    boundary = _HEADER_BOUNDARY.search(prefix)
    return prefix[: boundary.start()] if boundary else prefix[:2_000]


def derive_email_context(
    *,
    subject: str,
    sender: str,
    text: str,
    recipient_expected: bool = False,
) -> EmailContextSignals:
    """Derive non-sensitive context without trusting body claims as proof."""

    headers = _header_block(text)
    authentication_headers = " ".join(
        match.group(0) for match in _AUTHENTICATION_RESULTS.finditer(headers)
    ).lower()
    sender_domain = sender.rsplit("@", 1)[-1].strip(" >").lower()
    authentication_passed = "dmarc=pass" in authentication_headers or (
        "dkim=pass" in authentication_headers
        and bool(sender_domain)
        and sender_domain in authentication_headers
    )
    has_list_id = re.search(r"(?im)^list-id\s*:", headers) is not None
    has_unsubscribe = re.search(r"(?im)^list-unsubscribe\s*:", headers) is not None
    return EmailContextSignals(
        structured_forward=bool(
            _FORWARD_SUBJECT.search(subject)
            and _FORWARD_MARKER.search(text[:10_000])
        ),
        outer_sender_authenticated=authentication_passed,
        mailing_list_headers=has_list_id and has_unsubscribe,
        subscription_claimed=_SUBSCRIPTION_CLAIM.search(text[:10_000]) is not None,
        recipient_expected=recipient_expected,
        transactional_evidence=_has_transactional_calendar(text),
    )
