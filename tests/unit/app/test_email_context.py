"""Regression coverage for privacy-safe email context derivation."""

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
