from __future__ import annotations

from data_platform.services.common_crawl_signal_synthetic import (
    CommonCrawlSignalSyntheticService,
)


def test_common_crawl_signal_synthetic_builds_phishing_drafts() -> None:
    payload = {
        "candidates": [
            {
                "raw_record_id": "raw-1",
                "rule_key": "phishing_lure_candidate",
                "target_label": "phishing",
                "normalized_text": (
                    "Objet : Mondial Relay : votre colis reste en attente aujourd'hui\n\n"
                    "Bonjour,\n\n"
                    "Une tentative de livraison liée au dossier CL-DC60E3 reste suspendue après un échec de remise.\n\n"
                    "Merci d'effectuer la vérification demandée aujourd'hui.\n\n"
                    "Cordialement,\nMondial Relay"
                ),
            }
        ]
    }

    drafts = CommonCrawlSignalSyntheticService.build_drafts(
        payload, variants_per_seed=2
    )

    assert drafts["seed_count"] == 1
    assert drafts["draft_count"] == 2
    assert all(draft["target_label"] == "phishing" for draft in drafts["drafts"])
    assert all(
        draft["nearest_reference_raw_record_id"] == "raw-1"
        for draft in drafts["drafts"]
    )
    assert all("[LIEN_" in draft["normalized_text"] for draft in drafts["drafts"])
    assert any(
        "Cellule de suivi livraison" in draft["normalized_text"]
        for draft in drafts["drafts"]
    )


def test_common_crawl_signal_synthetic_builds_generation_samples() -> None:
    payload = {
        "drafts": [
            {
                "draft_id": "draft-1",
                "scenario_id": "delivery:mondial_relay",
                "variant_index": 0,
                "parent_source": "common-crawl-bigdata",
                "target_label": "phishing",
                "primary_theme": "delivery",
                "review_state": "usable",
                "review_notes": [],
                "text_sha256": "hash-1",
                "nearest_reference_raw_record_id": "raw-1",
                "nearest_similarity": 1.0,
            }
        ]
    }

    samples = CommonCrawlSignalSyntheticService.build_generation_samples(payload)

    assert len(samples) == 1
    assert samples[0]["source_name"] == "common-crawl-phishing-signal"
    assert samples[0]["target_label"] == "phishing"
