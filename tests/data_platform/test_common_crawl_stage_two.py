from __future__ import annotations

from data_platform.services.common_crawl_stage_two import CommonCrawlStageTwoService


def test_common_crawl_stage_two_accepts_transactional_legitimate() -> None:
    result = CommonCrawlStageTwoService.review(
        (
            "Accéder au Menu Principal Réinitialiser votre mot de passe. "
            "Veuillez renseigner le formulaire ci-dessous. "
            "Vous recevrez votre mot de passe provisoire par SMS."
        ),
        {"category": "legitimate"},
    )

    assert result.route_outcome == "accepted"
    assert result.route_subtype == "transactional_legitimate"
    assert result.derived_payload is not None
    assert result.derived_payload["promotion_eligible"] is True


def test_common_crawl_stage_two_marks_promotional_spam_candidate() -> None:
    result = CommonCrawlStageTwoService.review(
        "Bonjour, profitez de notre offre exclusive avec réduction immédiate et code promo newsletter.",
        {"category": "spam_like", "query": "newsletter"},
    )

    assert result.route_outcome == "specialized_processing"
    assert result.route_reason == "common_crawl_promotional_candidate"
    assert result.route_subtype == "promotional_spam"
    assert result.derived_payload is not None
    assert result.derived_payload["candidate_subtype"] == "promotional_spam"


def test_common_crawl_stage_two_accepts_nested_transactional_window() -> None:
    result = CommonCrawlStageTwoService.review(
        (
            "Accéder au Menu Principal Accéder au Contenu éditorial Réinitialiser votre mot de passe "
            "Nous vous aidons à récupérer votre mot de passe en cas de perte, vol, oubli ou à sécuriser l'accès à votre espace client internet. "
            "Choisissez l'envoi du mot de passe provisoire par SMS. Vous recevrez ensuite un code à usage unique sur votre numéro de téléphone mobile. "
            "Accéder au Pied de page"
        ),
        {"category": "legitimate"},
    )

    assert result.route_outcome == "accepted"
    assert result.route_subtype == "transactional_legitimate"
    assert "mot de passe provisoire" in result.extracted_text


def test_common_crawl_stage_two_demotes_product_page_with_delivery_signals() -> None:
    result = CommonCrawlStageTwoService.review(
        (
            "Un accès à la gestion des comptes via votre Espace Client Internet Pour 1€/mois Découvrir la formule de compte. "
            "L'alerte SMS vous informe automatiquement de la situation de vos comptes et vous recevrez une notification sur votre messagerie personnelle."
        ),
        {"category": "legitimate"},
    )

    assert result.route_outcome == "specialized_processing"
    assert result.route_reason == "common_crawl_instructional_candidate"
    assert result.route_subtype == "instructional_legitimate"
