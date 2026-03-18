from __future__ import annotations

from sicurre_api.domains.data_platform.services.normalization import (
    TextNormalizationService,
    anonymize_pii,
    clean_text,
)


def test_anonymize_pii_replaces_sensitive_tokens() -> None:
    text = "Contact: jean.dupont@example.com, 06 12 34 56 78, https://evil.test"

    result = anonymize_pii(text)

    assert "[EMAIL]" in result
    assert "[PHONE]" in result
    assert "[URL]" in result


def test_clean_text_removes_html_and_normalizes_spacing() -> None:
    text = "<p>Bonjour&nbsp;&nbsp;monde</p>\n\n\n"

    result = clean_text(text)

    assert result == "Bonjour monde"


def test_normalize_text_marks_short_text_unusable() -> None:
    service = TextNormalizationService()

    result = service.normalize_text("trop court")

    assert result.is_usable is False
    assert result.rejection_reason == "text_too_short"


def test_normalize_text_sets_redaction_flag() -> None:
    service = TextNormalizationService()

    result = service.normalize_text(
        "Veuillez écrire à jean.dupont@example.com pour confirmer votre abonnement premium avant expiration definitive."
    )

    assert result.is_usable is True
    assert result.contains_redaction_tokens is True
    assert "[EMAIL]" in result.cleaned_text
