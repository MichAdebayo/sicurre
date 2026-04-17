from __future__ import annotations

from data_platform.services.normalization_pipeline import NormalizationPipeline
from db.models.lineage import NormalizedLabel, RedactionStatus


def test_source_policy_marks_phishtank_as_url_intelligence_only() -> None:
    policy = NormalizationPipeline.get_source_policy("phishtank-online-valid")

    assert policy is not None
    assert policy.normalize_messages is False
    assert policy.reason == "url_intelligence_source"


def test_source_policy_marks_enron_as_adaptation_only() -> None:
    policy = NormalizationPipeline.get_source_policy("enron_spam")

    assert policy is not None
    assert policy.normalize_messages is False
    assert policy.reason == "english_adaptation_source"


def test_database_historical_filter_includes_database_child_sources() -> None:
    sources = {
        "parent": "database-historical",
        "faker": "database/faker/synthetic_phishing_medium",
        "adapted": "database/adapted/adapted_en_fr",
        "other": "common-crawl-bigdata",
    }

    assert NormalizationPipeline._resolve_target_source_ids(
        sources,
        "database-historical",
    ) == {"parent", "faker", "adapted"}


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
    assert payload.route_outcome == "specialized_processing"
    assert payload.route_reason == "common_crawl_no_window_holdout"
    assert payload.route_subtype == "no_window_holdout"
    assert len(payload.text) <= 10_003


def test_common_crawl_extracts_transactional_window_when_message_like() -> None:
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload(
        "common-crawl-bigdata",
        {
            "text": (
                "Accéder au Menu Principal Accéder au Contenu éditorial Réinitialiser votre mot de passe "
                "Nous vous aidons à récupérer votre mot de passe en cas de perte ou d'oubli. "
                "Pour réinitialiser votre mot de passe, veuillez renseigner le formulaire ci-dessous. "
                "Vous recevrez votre mot de passe provisoire par SMS si votre numéro de téléphone sécurisé est à jour. "
                "Sinon, vous le recevrez par courrier. Articles associés"
            ),
            "label": 0,
        },
    )

    assert payload.label is NormalizedLabel.LEGITIMATE
    assert payload.route_outcome == "accepted"
    assert payload.route_subtype == "transactional_legitimate"
    assert payload.text is not None
    assert "Vous recevrez votre mot de passe provisoire par SMS" in payload.text
    assert "Accéder au Menu Principal" not in payload.text


def test_common_crawl_awareness_page_stays_specialized() -> None:
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload(
        "common-crawl-bigdata",
        {
            "text": (
                "Accéder au Menu Principal Comment me protéger des risques de vol de mes données carte bancaire ? "
                "A réception de mail, de sms ou d'appels douteux, ne renseignez jamais vos données bancaires et personnelles. "
                "Voici quelques conseils pour vous protéger des escroqueries par e-mail et SMS."
            ),
            "label": 0,
        },
    )

    assert payload.route_outcome == "specialized_processing"
    assert payload.route_reason == "common_crawl_awareness_content"
    assert payload.route_subtype == "awareness_or_report"


def test_common_crawl_navigation_heavy_page_gets_holdout_subtype() -> None:
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload(
        "common-crawl-bigdata",
        {
            "text": (
                "Accéder au Menu Principal Accéder au pied de page Devenir client Mon espace "
                "Partagez Imprimer Lecture 4 min Découvrez nos services et consultez nos articles associés."
            ),
            "label": 0,
            "category": "legitimate",
        },
    )

    assert payload.route_outcome == "specialized_processing"
    assert payload.route_reason == "common_crawl_navigation_heavy_holdout"
    assert payload.route_subtype == "navigation_heavy_holdout"


def test_common_crawl_promotional_candidate_gets_spam_subtype() -> None:
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload(
        "common-crawl-bigdata",
        {
            "text": (
                "Bonjour, profitez de notre offre exclusive avec une réduction immédiate "
                "et un code promo réservé aux abonnés newsletter."
            ),
            "label": "spam_like",
            "category": "spam_like",
        },
    )

    assert payload.route_outcome == "specialized_processing"
    assert payload.route_reason == "common_crawl_promotional_candidate"
    assert payload.route_subtype == "promotional_spam"


def test_common_crawl_nested_message_inside_navigation_page_is_recovered() -> None:
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload(
        "common-crawl-bigdata",
        {
            "text": (
                "Accéder au Menu Principal Accéder au Contenu éditorial Comment sécuriser mon espace client ? "
                "Réinitialiser votre mot de passe. Choisissez l'envoi du mot de passe provisoire par SMS. "
                "Vous recevrez ensuite un code à usage unique sur votre numéro de téléphone mobile. "
                "Articles associés Accéder au Pied de page"
            ),
            "category": "legitimate",
        },
    )

    assert payload.label is NormalizedLabel.LEGITIMATE
    assert payload.route_outcome == "accepted"
    assert payload.route_subtype == "transactional_legitimate"
    assert payload.text is not None
    assert "mot de passe provisoire" in payload.text


def test_common_crawl_product_page_is_not_directly_accepted() -> None:
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload(
        "common-crawl-bigdata",
        {
            "text": (
                "Un accès à la gestion des comptes via votre Espace Client Internet Pour 1€/mois Découvrir la formule de compte. "
                "L'alerte SMS vous informe automatiquement de la situation de vos comptes et vous recevrez une notification sur votre messagerie personnelle."
            ),
            "category": "legitimate",
        },
    )

    assert payload.route_outcome == "specialized_processing"
    assert payload.route_reason == "common_crawl_instructional_candidate"
    assert payload.route_subtype == "instructional_legitimate"


def test_common_crawl_phishing_related_payload_maps_to_phishing_lane() -> None:
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload(
        "common-crawl-bigdata",
        {
            "text": (
                "Ensemble contre les Arnaques Site internet frauduleux Page miroir mondial Relay. "
                "Aucun livreur n'est passé pendant cette plage horaire. "
                "Message reçu ce jour. Escroquerie au faux colis."
            ),
            "label": "scam_reports_fr",
            "category": "phishing_related",
            "query": "signal-arnaques.com/*",
            "query_label": "scam_reports_fr",
            "url": "https://www.signal-arnaques.com/",
        },
    )

    assert payload.label is NormalizedLabel.PHISHING
    assert payload.route_outcome == "specialized_processing"
    assert payload.route_reason == "common_crawl_phishing_lure_candidate"
    assert payload.route_subtype == "phishing_lure_candidate"


def test_common_crawl_phishing_awareness_payload_maps_to_awareness_lane() -> None:
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload(
        "common-crawl-bigdata",
        {
            "text": (
                "Assistance aux victimes de cybermalveillance. Cybermalveillance.gouv.fr a pour missions "
                "de sensibiliser au risque cyber, d'informer sur les menaces numériques et les moyens de s'en protéger."
            ),
            "label": "cert_gov_fr",
            "category": "phishing_related",
            "query": "cybermalveillance.gouv.fr/*",
            "query_label": "cert_gov_fr",
            "url": "https://www.cybermalveillance.gouv.fr/",
        },
    )

    assert payload.label is NormalizedLabel.PHISHING
    assert payload.route_outcome == "specialized_processing"
    assert payload.route_reason == "common_crawl_phishing_awareness_content"
    assert payload.route_subtype == "awareness_or_report"


def test_extract_payload_rejects_certfr_report_like_documents() -> None:
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload(
        "cert-fr-cti",
        {
            "text": "PANORAMA DE LA CYBERMENACE 2025 TLP:CLEAR Table des matières ANSSI Premier Ministre",
        },
    )

    assert payload.text is not None
    assert payload.label is NormalizedLabel.PHISHING
    assert payload.route_outcome == "specialized_processing"
    assert payload.route_reason == "certfr_threat_intel_requires_extraction"
    assert payload.route_subtype == "threat_intel"


def test_certfr_notification_context_without_embedded_message_stays_specialized() -> (
    None
):
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload(
        "cert-fr-cti",
        {
            "text": (
                "La notification se traduit par la réception d'un iMessage et d'un courriel d'alerte envoyé par Apple depuis l'adresse threat-notifications@email.apple.com. "
                "Il est important de prendre en compte rapidement ces notifications et de mettre en oeuvre les mesures adéquates."
            ),
        },
    )

    assert payload.text is not None
    assert "[EMAIL]" in payload.text
    assert payload.route_outcome == "specialized_processing"
    assert payload.route_reason == "certfr_notification_context_only"
    assert payload.route_subtype == "procedural_notification"


def test_certfr_embedded_message_routes_to_synthetic_lure_review() -> None:
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload(
        "cert-fr-cti",
        {
            "text": (
                "Objet: Vérification urgente Bonjour, veuillez confirmer votre compte sans délai. "
                "Cliquez sur le lien sécurisé pour éviter la suspension de votre accès."
            ),
        },
    )

    assert payload.label is NormalizedLabel.PHISHING
    assert payload.route_outcome == "specialized_processing"
    assert payload.route_reason == "certfr_synthetic_lure_candidate"
    assert payload.route_subtype == "synthetic_lure_candidate"


def test_classify_transformation_detects_no_change() -> None:
    strength, similarity = NormalizationPipeline._classify_transformation(
        "Bonjour merci de confirmer votre compte",
        "Bonjour merci de confirmer votre compte",
    )

    assert strength == "none"
    assert similarity == 1.0


def test_extract_review_text_for_phishtank_uses_url_fields() -> None:
    preview = NormalizationPipeline._extract_review_text(
        "phishtank-online-valid",
        {
            "url": "https://example.test/login",
            "domain": "example.test",
            "label": "phishing",
            "filter_reason": "brand:test",
        },
    )

    assert "https://example.test/login" in preview
    assert "brand:test" in preview


def test_database_historical_maps_subsource_labels() -> None:
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    phishing_payload = pipeline.extract_payload(
        "database-historical",
        {
            "source": "synthetic_phishing_medium",
            "subject": "Votre compte a ete bloque",
            "body": "Bonjour, veuillez confirmer votre compte immediatement.",
            "label": 0,
        },
    )
    spam_payload = pipeline.extract_payload(
        "database-historical",
        {
            "source": "crowdsourced_spam_spam_4",
            "subject": "Promo exceptionnelle",
            "body": "Bonjour, offre gratuite reservee aujourd'hui.",
            "label": 0,
        },
    )

    assert phishing_payload.label is NormalizedLabel.PHISHING
    assert spam_payload.label is NormalizedLabel.SPAM


def test_database_child_source_path_uses_historical_policy() -> None:
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload(
        "database/faker/synthetic_phishing_medium",
        {
            "source": "database/faker/synthetic_phishing_medium",
            "subject": "Votre compte a ete bloque",
            "body": "Bonjour, veuillez confirmer votre compte immediatement.",
            "label": 0,
        },
    )

    assert payload.label is NormalizedLabel.PHISHING
    assert payload.route_outcome == "accepted"
    assert "historical_subsource:synthetic_phishing_medium" in payload.trace_steps


def test_database_historical_routes_corrupted_text_to_specialized_processing() -> None:
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload(
        "database-historical",
        {
            "source": "crowdsourced_spam_spam_4",
            "subject": "Qualcuno ha messo like al tuo profilo рџ",
            "body": "<!DOCTYPE html><html lang='en'><title>Register now free spins</title>",
            "label": 0,
        },
    )

    assert payload.route_outcome == "specialized_processing"
    assert payload.route_reason in {
        "historical_repair_needed",
        "historical_language_recheck_required",
    }


def test_database_historical_routes_english_footer_spam_to_specialized_processing() -> (
    None
):
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload(
        "database-historical",
        {
            "source": "crowdsourced_spam_spam_3",
            "subject": "Votre accès Cloud sera interrompu sans mise à jour",
            "body": "Top Stories of the Day: Sep 0, 2019 ----- If you believe this has been sent to you in error, please safely unsubscribe",
            "label": 0,
        },
    )

    assert payload.route_outcome == "specialized_processing"
    assert payload.route_reason == "historical_content_too_thin"
