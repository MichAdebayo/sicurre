from __future__ import annotations

from data_platform.services.common_crawl_promotion_review import (
    CommonCrawlPromotionReviewService,
)


def test_common_crawl_promotion_review_builds_plan() -> None:
    payload = {
        "source_name": "common-crawl-bigdata",
        "result": {
            "parent_sources": {
                "bigdata": [
                    {
                        "samples": [
                            {
                                "raw_record_id": "a",
                                "route_outcome": "accepted",
                                "route_subtype": "transactional_legitimate",
                                "similarity_score": 0.4,
                                "normalized_length": 500,
                                "transformation_strength": "major",
                                "derived_payload": {"promotion_eligible": True},
                            },
                            {
                                "raw_record_id": "b",
                                "route_outcome": "specialized_processing",
                                "route_subtype": "instructional_legitimate",
                                "similarity_score": 0.3,
                                "normalized_length": 650,
                                "transformation_strength": "major",
                                "derived_payload": {"promotion_eligible": False},
                            },
                        ],
                        "route_summary": {"accepted": 1, "specialized_processing": 1},
                        "subtype_summary": {
                            "transactional_legitimate": 1,
                            "instructional_legitimate": 1,
                        },
                        "rejection_summary": {
                            "common_crawl_requires_chunk_extraction": 1,
                        },
                    }
                ]
            }
        },
    }

    plan = CommonCrawlPromotionReviewService.build_plan(payload)

    assert plan["autopromotable_count"] == 1
    assert plan["manual_review_count"] == 1
    assert plan["autopromotable_record_ids"] == ["a"]
    assert plan["manual_review_record_ids"] == ["b"]


def test_common_crawl_acceptance_review_rejects_non_comparable_subtypes() -> None:
    payload = {
        "candidates": [
            {
                "candidate_id": "cand-awareness",
                "draft_id": "draft-awareness",
                "raw_record_id": "raw-awareness",
                "source_name": "common-crawl-bigdata",
                "rule_key": "awareness_or_report",
                "rewrite_mode": "awareness_page_to_warning_notification",
                "target_label": "legitimate",
                "review_state": "usable",
                "review_notes": [],
                "quality_signals": {
                    "french_marker_count": 5,
                    "target_cue_hits": 3,
                },
                "text_length": 410,
                "text_sha256": "hash-awareness",
                "normalized_text": "Objet : Vigilance renforcée concernant les messages suspects\n\nBonjour, restez vigilant.",
                "contains_pii": False,
                "redaction_status": "not_required",
            }
        ]
    }

    review = CommonCrawlPromotionReviewService.build_acceptance_review(payload)

    assert review["accepted_candidate_count"] == 0
    assert review["rejection_summary"]["subtype_not_comparable_to_direct_write"] == 1


def test_common_crawl_acceptance_review_accepts_clean_promotional_candidate() -> None:
    payload = {
        "candidates": [
            {
                "candidate_id": "cand-spam",
                "draft_id": "draft-spam",
                "raw_record_id": "raw-spam",
                "source_name": "common-crawl-bigdata",
                "rule_key": "promotional_spam",
                "rewrite_mode": "promotional_page_to_spam_message",
                "target_label": "spam",
                "review_state": "usable",
                "review_notes": [],
                "quality_signals": {
                    "french_marker_count": 4,
                    "target_cue_hits": 1,
                },
                "text_length": 420,
                "text_sha256": "hash-spam",
                "normalized_text": "Objet : Offre prioritaire aujourd'hui\n\nBonjour, profitez dès maintenant de cette offre avec des conditions simplifiées. Répondez à ce message pour recevoir les détails.\n\nÀ très vite,\nService commercial",
                "contains_pii": False,
                "redaction_status": "not_required",
            }
        ]
    }

    review = CommonCrawlPromotionReviewService.build_acceptance_review(payload)

    assert review["accepted_candidate_count"] == 1
    assert review["accepted_label_summary"]["spam"] == 1
    assert review["proposed_normalized_messages"][0]["raw_record_id"] == "raw-spam"
    assert review["proposed_annotations"][0]["label"] == "spam"


def test_common_crawl_acceptance_review_rejects_grammar_residue() -> None:
    payload = {
        "candidates": [
            {
                "candidate_id": "cand-legit",
                "draft_id": "draft-legit",
                "raw_record_id": "raw-legit",
                "source_name": "common-crawl-bigdata",
                "rule_key": "instructional_legitimate",
                "rewrite_mode": "institutional_page_to_notification",
                "target_label": "legitimate",
                "review_state": "usable",
                "review_notes": [],
                "quality_signals": {
                    "french_marker_count": 5,
                    "target_cue_hits": 2,
                },
                "text_length": 390,
                "text_sha256": "hash-legit",
                "normalized_text": "Objet : Rappel pratique au sujet de les messages suspects\n\nBonjour, utilisez vos canaux habituels.",
                "contains_pii": False,
                "redaction_status": "not_required",
            }
        ]
    }

    review = CommonCrawlPromotionReviewService.build_acceptance_review(payload)

    assert review["accepted_candidate_count"] == 0
    assert review["rejection_summary"]["grammar_residue_detected"] == 1


def test_common_crawl_acceptance_review_rejects_promotional_page_residue() -> None:
    payload = {
        "candidates": [
            {
                "candidate_id": "cand-promo-residue",
                "draft_id": "draft-promo-residue",
                "raw_record_id": "raw-promo-residue",
                "source_name": "common-crawl-bigdata",
                "rule_key": "promotional_spam",
                "rewrite_mode": "promotional_page_to_spam_message",
                "target_label": "spam",
                "review_state": "usable",
                "review_notes": [],
                "quality_signals": {
                    "french_marker_count": 4,
                    "target_cue_hits": 2,
                },
                "text_length": 430,
                "text_sha256": "hash-promo-residue",
                "normalized_text": "Objet : Questions Diverses - Ferry Cdiscount Ce site : votre offre réservée jusqu'à ce soir\n\nBonjour, profitez dès maintenant de cette offre.",
                "contains_pii": False,
                "redaction_status": "not_required",
            }
        ]
    }

    review = CommonCrawlPromotionReviewService.build_acceptance_review(payload)

    assert review["accepted_candidate_count"] == 0
    assert review["rejection_summary"]["promotional_page_residue_detected"] == 1


def test_common_crawl_acceptance_review_rejects_malformed_subject_fragment() -> None:
    payload = {
        "candidates": [
            {
                "candidate_id": "cand-malformed-subject",
                "draft_id": "draft-malformed-subject",
                "raw_record_id": "raw-malformed-subject",
                "source_name": "common-crawl-bigdata",
                "rule_key": "instructional_legitimate",
                "rewrite_mode": "institutional_page_to_notification",
                "target_label": "legitimate",
                "review_state": "usable",
                "review_notes": [],
                "quality_signals": {
                    "french_marker_count": 5,
                    "target_cue_hits": 2,
                },
                "text_length": 390,
                "text_sha256": "hash-malformed-subject",
                "normalized_text": "Objet : Point d'information sur découvrez les essentiels de certicode plus (pdf\n\nBonjour, utilisez uniquement vos canaux habituels.",
                "contains_pii": False,
                "redaction_status": "not_required",
            }
        ]
    }

    review = CommonCrawlPromotionReviewService.build_acceptance_review(payload)

    assert review["accepted_candidate_count"] == 0
    assert review["rejection_summary"]["malformed_subject_fragment_detected"] == 1


def test_common_crawl_acceptance_review_rejects_imperative_subject_fragment() -> None:
    payload = {
        "candidates": [
            {
                "candidate_id": "cand-imperative-subject",
                "draft_id": "draft-imperative-subject",
                "raw_record_id": "raw-imperative-subject",
                "source_name": "common-crawl-bigdata",
                "rule_key": "instructional_legitimate",
                "rewrite_mode": "institutional_page_to_notification",
                "target_label": "legitimate",
                "review_state": "usable",
                "review_notes": [],
                "quality_signals": {
                    "french_marker_count": 5,
                    "target_cue_hits": 2,
                },
                "text_length": 390,
                "text_sha256": "hash-imperative-subject",
                "normalized_text": "Objet : Rappel utile concernant pour faire un virement, cliquez de la\n\nBonjour, utilisez uniquement vos canaux habituels.",
                "contains_pii": False,
                "redaction_status": "not_required",
            }
        ]
    }

    review = CommonCrawlPromotionReviewService.build_acceptance_review(payload)

    assert review["accepted_candidate_count"] == 0
    assert review["rejection_summary"]["malformed_subject_fragment_detected"] == 1
