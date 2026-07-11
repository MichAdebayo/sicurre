from __future__ import annotations

from data_platform.services.certfr.review_staging import CertFRReviewStagingService


def test_certfr_review_staging_groups_samples() -> None:
    payload = {
        "source_name": "cert-fr-cti",
        "result": {
            "parent_sources": {
                "scraping": [
                    {
                        "samples": [
                            {
                                "raw_record_id": "a",
                                "route_subtype": "threat_intel",
                                "route_reason": "certfr_threat_intel_requires_extraction",
                                "normalized_length": 1400,
                                "derived_payload": {
                                    "ioc_counts": {
                                        "domains": 1,
                                        "emails": 0,
                                        "ips": 0,
                                        "hashes": 0,
                                    },
                                    "phishing_relevance": True,
                                },
                            },
                            {
                                "raw_record_id": "b",
                                "route_subtype": "synthetic_lure_candidate",
                                "route_reason": "certfr_synthetic_lure_candidate",
                                "normalized_length": 180,
                                "derived_payload": {"is_synthetic": True},
                            },
                        ],
                        "subtype_summary": {
                            "threat_intel": 1,
                            "synthetic_lure_candidate": 1,
                        },
                        "rejection_summary": {
                            "certfr_threat_intel_requires_extraction": 1,
                            "certfr_synthetic_lure_candidate": 1,
                        },
                    }
                ]
            }
        },
    }

    staged = CertFRReviewStagingService.build_stage_payload(payload)

    assert staged["ioc_enriched_threat_intel_samples"] == 1
    assert staged["phishing_relevant_threat_intel_samples"] == 1
    assert staged["synthetic_lure_candidate_count"] == 1
    assert len(staged["staged_samples"]["threat_intel"]) == 1
