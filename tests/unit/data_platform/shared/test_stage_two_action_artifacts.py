from __future__ import annotations

from data_platform.services.shared.stage_two_action_artifacts import (
    StageTwoActionArtifactsService,
)


def test_stage_two_action_artifacts_split_rules_into_outputs() -> None:
    artifacts = StageTwoActionArtifactsService.build_artifacts(
        matrix_payload={
            "sources": [
                {
                    "source_name": "common-crawl-bigdata",
                    "rows": [
                        {
                            "key_type": "route_subtype",
                            "key": "instructional_legitimate",
                            "action": "adapt",
                            "output_bucket": "adaptation_queue",
                            "adaptation_fit": "high",
                            "rationale": "rewrite page into message",
                            "current_count": 2,
                        },
                        {
                            "key_type": "route_subtype",
                            "key": "awareness_or_report",
                            "action": "extract_signals_only",
                            "output_bucket": "signal_bank",
                            "adaptation_fit": "low",
                            "rationale": "keep lexical signals only",
                            "current_count": 1,
                        },
                        {
                            "key_type": "route_subtype",
                            "key": "navigation_heavy_holdout",
                            "action": "archive",
                            "output_bucket": "dead_holdout_archive",
                            "adaptation_fit": "none",
                            "rationale": "too much chrome",
                            "current_count": 3,
                        },
                    ],
                }
            ]
        },
        review_payloads=[
            {
                "source_name": "common-crawl-bigdata",
                "result": {
                    "parent_sources": {
                        "bigdata": [
                            {
                                "samples": [
                                    {
                                        "raw_record_id": "adapt-1",
                                        "route_subtype": "instructional_legitimate",
                                        "route_reason": "common_crawl_requires_chunk_extraction",
                                        "rejection_reason": "common_crawl_requires_chunk_extraction",
                                        "extracted_label": "legitimate",
                                        "normalized_preview": "Conseils utiles",
                                        "transformation_strength": "major",
                                        "similarity_score": 0.3,
                                        "normalized_length": 700,
                                        "trace_summary": "trace",
                                        "derived_payload": {
                                            "promotion_eligible": False
                                        },
                                    },
                                    {
                                        "raw_record_id": "signal-1",
                                        "route_subtype": "awareness_or_report",
                                        "route_reason": "common_crawl_awareness_content",
                                        "rejection_reason": "common_crawl_awareness_content",
                                        "extracted_label": "legitimate",
                                        "normalized_preview": "Ne communiquez jamais vos donnees",
                                        "transformation_strength": "major",
                                        "similarity_score": 0.4,
                                        "normalized_length": 500,
                                        "trace_summary": "trace",
                                        "derived_payload": {
                                            "promotion_eligible": False
                                        },
                                    },
                                    {
                                        "raw_record_id": "archive-1",
                                        "route_subtype": "navigation_heavy_holdout",
                                        "route_reason": "common_crawl_navigation_heavy_holdout",
                                        "rejection_reason": "common_crawl_navigation_heavy_holdout",
                                        "extracted_label": "legitimate",
                                        "normalized_preview": "Navigation",
                                        "transformation_strength": "major",
                                        "similarity_score": 0.5,
                                        "normalized_length": 2500,
                                        "trace_summary": "trace",
                                        "derived_payload": {
                                            "promotion_eligible": False
                                        },
                                    },
                                ]
                            }
                        ]
                    }
                },
            }
        ],
    )

    adaptation_rules = artifacts["adaptation_queue"]["sources"][0]["rules"]
    signal_rules = artifacts["signal_bank"]["sources"][0]["rules"]
    archive_rules = artifacts["archive_manifest"]["sources"][0]["rules"]

    assert artifacts["adaptation_queue"]["total_candidate_count"] == 2
    assert adaptation_rules[0]["sampled_record_count"] == 1
    assert adaptation_rules[0]["sampled_records"][0]["raw_record_id"] == "adapt-1"

    assert artifacts["signal_bank"]["total_candidate_count"] == 1
    assert signal_rules[0]["sampled_records"][0]["raw_record_id"] == "signal-1"

    assert artifacts["archive_manifest"]["total_candidate_count"] == 3
    assert archive_rules[0]["sampled_records"][0]["raw_record_id"] == "archive-1"


def test_stage_two_action_artifacts_render_markdown() -> None:
    markdown = StageTwoActionArtifactsService.render_markdown(
        {
            "adaptation_queue": {
                "generated_at": "2026-04-07T00:00:00+00:00",
                "total_candidate_count": 2,
                "sampled_record_count": 1,
                "sources": [],
            },
            "signal_bank": {
                "generated_at": "2026-04-07T00:00:00+00:00",
                "total_candidate_count": 1,
                "sampled_record_count": 1,
                "sources": [],
            },
            "archive_manifest": {
                "generated_at": "2026-04-07T00:00:00+00:00",
                "total_candidate_count": 3,
                "sampled_record_count": 1,
                "sources": [],
            },
        }
    )

    assert "# Stage-Two Downstream Artifacts" in markdown
    assert "Adaptation Queue" in markdown
    assert "Signal Bank" in markdown
    assert "Archive Manifest" in markdown


def test_stage_two_action_artifacts_deduplicates_adaptation_samples_by_preview() -> (
    None
):
    artifacts = StageTwoActionArtifactsService.build_artifacts(
        matrix_payload={
            "sources": [
                {
                    "source_name": "common-crawl-bigdata",
                    "rows": [
                        {
                            "key_type": "route_subtype",
                            "key": "promotional_spam",
                            "action": "adapt",
                            "output_bucket": "adaptation_queue",
                            "adaptation_fit": "high",
                            "rationale": "rewrite page into spam",
                            "current_count": 2,
                        }
                    ],
                }
            ]
        },
        review_payloads=[
            {
                "source_name": "common-crawl-bigdata",
                "result": {
                    "parent_sources": {
                        "bigdata": [
                            {
                                "samples": [
                                    {
                                        "raw_record_id": "promo-1",
                                        "route_subtype": "promotional_spam",
                                        "route_reason": "common_crawl_promotional_candidate",
                                        "rejection_reason": "common_crawl_promotional_candidate",
                                        "extracted_label": "spam",
                                        "normalized_preview": "Profitez de notre offre exclusive aujourd'hui.",
                                        "transformation_strength": "major",
                                        "similarity_score": 0.3,
                                        "normalized_length": 80,
                                        "trace_summary": "trace",
                                        "derived_payload": {},
                                    },
                                    {
                                        "raw_record_id": "promo-2",
                                        "route_subtype": "promotional_spam",
                                        "route_reason": "common_crawl_promotional_candidate",
                                        "rejection_reason": "common_crawl_promotional_candidate",
                                        "extracted_label": "spam",
                                        "normalized_preview": "Profitez de notre offre exclusive aujourd'hui.",
                                        "transformation_strength": "major",
                                        "similarity_score": 0.4,
                                        "normalized_length": 100,
                                        "trace_summary": "trace",
                                        "derived_payload": {},
                                    },
                                ]
                            }
                        ]
                    }
                },
            }
        ],
    )

    rules = artifacts["adaptation_queue"]["sources"][0]["rules"]
    assert rules[0]["sampled_record_count"] == 1
    assert rules[0]["sampled_records"][0]["raw_record_id"] == "promo-2"
