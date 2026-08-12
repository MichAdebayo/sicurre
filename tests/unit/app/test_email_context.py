"""Regression coverage for privacy-safe email context derivation."""

from typing import Any

import pytest

from data_platform.services import email_context
from data_platform.services.email_context import derive_email_context


def test_detects_authenticated_structured_subscribed_forward() -> None:
    text = """Authentication-Results: mx.cloudflare.net;
 dkim=pass header.d=gmail.com; dmarc=pass

---------- Forwarded message ---------
From: Newsletter <news@example.fr>
Subject: Actualités

You are receiving this newsletter because you subscribed.
"""

    context = derive_email_context(
        subject="Fwd: Actualités",
        sender="Friend <friend@gmail.com>",
        text=text,
    )

    assert context.structured_forward is True
    assert context.outer_sender_authenticated is True
    assert context.subscription_claimed is True
    assert context.recipient_expected is False
    assert context.transactional_evidence is False


def test_subject_or_subscription_claim_alone_is_not_a_structured_forward() -> None:
    context = derive_email_context(
        subject="Fwd: Vérifiez votre compte",
        sender="attacker@example.test",
        text="You are receiving this because you subscribed. Connectez-vous immédiatement.",
    )

    assert context.structured_forward is False
    assert context.outer_sender_authenticated is False
    assert context.subscription_claimed is True


def test_requires_both_list_headers_for_mailing_list_signal() -> None:
    complete = derive_email_context(
        subject="Newsletter",
        sender="news@example.fr",
        text=(
            "List-ID: Example News <news.example.fr>\n"
            "List-Unsubscribe: <https://example.fr/unsubscribe>\n\nBonjour"
        ),
    )
    partial = derive_email_context(
        subject="Newsletter",
        sender="news@example.fr",
        text="List-Unsubscribe: <https://example.fr/unsubscribe>\n\nBonjour",
    )

    assert complete.mailing_list_headers is True
    assert partial.mailing_list_headers is False


def test_body_authentication_claim_is_not_transport_evidence() -> None:
    context = derive_email_context(
        subject="Rapport",
        sender="attacker@example.test",
        text="Notre contrôle indique dmarc=pass et dkim=pass pour example.test.",
    )

    assert context.outer_sender_authenticated is False


def test_detects_coherent_calendar_mime_as_transactional_evidence() -> None:
    context = derive_email_context(
        subject="Accès au webinaire",
        sender="events@example.fr",
        recipient_expected=True,
        text=(
            "Authentication-Results: mx.example; dmarc=pass\n"
            "Content-Type: text/calendar; method=REQUEST; charset=utf-8\n\n"
            "BEGIN:VCALENDAR\nMETHOD:REQUEST\nBEGIN:VEVENT\n"
            "UID:event-42@example.fr\nDTSTART:20260814T090000Z\n"
            "END:VEVENT\nEND:VCALENDAR"
        ),
    )

    assert context.outer_sender_authenticated is True
    assert context.recipient_expected is True
    assert context.transactional_evidence is True


def test_calendar_wording_without_mime_structure_is_not_evidence() -> None:
    context = derive_email_context(
        subject="Invitation urgente",
        sender="attacker@example.test",
        text=(
            "Vous êtes inscrit. BEGIN:VCALENDAR METHOD:REQUEST "
            "BEGIN:VEVENT UID:x DTSTART:20260814T090000Z END:VEVENT END:VCALENDAR"
        ),
    )

    assert context.transactional_evidence is False


def test_malformed_message_is_not_transactional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenParser:
        def __init__(self, **_: Any) -> None:
            pass

        def parsestr(self, _: str) -> None:
            raise ValueError("malformed message")

    monkeypatch.setattr(email_context, "Parser", BrokenParser)

    assert email_context._has_transactional_calendar("invalid") is False


def test_unreadable_calendar_part_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenPart:
        def get_content_type(self) -> str:
            return "text/calendar"

        def get_content(self) -> str:
            raise ValueError("invalid calendar encoding")

    class ParsedMessage:
        def walk(self) -> list[BrokenPart]:
            return [BrokenPart()]

    class StubParser:
        def __init__(self, **_: Any) -> None:
            pass

        def parsestr(self, _: str) -> ParsedMessage:
            return ParsedMessage()

    monkeypatch.setattr(email_context, "Parser", StubParser)

    assert email_context._has_transactional_calendar("calendar") is False
