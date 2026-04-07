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
