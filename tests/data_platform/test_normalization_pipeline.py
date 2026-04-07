from __future__ import annotations

from data_platform.services.normalization_pipeline import NormalizationPipeline
from db.models.lineage import NormalizedLabel, RedactionStatus


def test_extract_payload_maps_sap_labs_registered_source_name() -> None:
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload(
        "sap-labs-blog",
        {
            "subject": "Mise a jour du compte",
            "body": "Bonjour, veuillez confirmer votre compte via jean.dupont@example.com.",
            "label": "phishing",
        },
    )

    assert payload.label is NormalizedLabel.PHISHING
    assert payload.text is not None
    assert "Objet : Mise a jour du compte" in payload.text
    assert "[EMAIL]" in payload.text
    assert payload.contains_pii is True
    assert payload.redaction_status is RedactionStatus.REDACTED


def test_extract_payload_maps_multilingual_kaggle_spam() -> None:
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload(
        "kaggle_multilingual_spam",
        {
            "text": "Bonjour, offre limitee a confirmer immediatement pour votre abonnement premium.",
            "label": "spam",
        },
    )

    assert payload.label is NormalizedLabel.SPAM
    assert payload.text is not None


def test_extract_payload_uses_hyphenated_common_crawl_source_name() -> None:
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload(
        "common-crawl-bigdata",
        {
            "text": "Accepter les cookies " + ("contenu bancaire utile " * 300),
            "label": 0,
        },
    )

    assert payload.label is NormalizedLabel.LEGITIMATE
    assert payload.text is not None
    assert "Accepter les cookies" not in payload.text
    assert len(payload.text) <= 10_003
