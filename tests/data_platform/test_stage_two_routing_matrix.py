from __future__ import annotations

from data_platform.services.stage_two_routing_matrix import (
    StageTwoRoutingMatrixService,
)


def test_stage_two_routing_matrix_assigns_counts_and_actions() -> None:
    matrix = StageTwoRoutingMatrixService.build_matrix(
        [
            {
                "source_name": "common-crawl-bigdata",
                "result": {
                    "parent_sources": {
                        "bigdata": [
                            {
                                "route_summary": {
                                    "accepted": 1,
                                    "specialized_processing": 5,
                                },
                                "subtype_summary": {
                                    "transactional_legitimate": 1,
                                    "instructional_legitimate": 2,
                                    "promotional_spam": 1,
                                    "awareness_or_report": 1,
                                    "navigation_heavy_holdout": 1,
                                    "no_window_holdout": 1,
                                },
                                "rejection_summary": {
                                    "common_crawl_instructional_candidate": 2,
                                },
                            }
                        ]
                    }
                },
            },
            {
                "source_name": "cert-fr-cti",
                "result": {
                    "parent_sources": {
                        "scraping": [
                            {
                                "route_summary": {
                                    "specialized_processing": 2,
                                },
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
            },
            {
                "source_name": "database-historical",
                "result": {
                    "parent_sources": {
                        "sql": [
                            {
                                "route_summary": {
                                    "accepted": 10,
                                    "specialized_processing": 3,
                                },
                                "subtype_summary": {},
                                "rejection_summary": {
                                    "historical_language_recheck_required": 2,
                                    "historical_repair_needed": 1,
                                },
                            }
                        ]
                    }
                },
            },
        ]
    )

    sources = {source["source_name"]: source for source in matrix["sources"]}

    common_crawl_rows = {
        row["key"]: row for row in sources["common-crawl-bigdata"]["rows"]
    }
    assert common_crawl_rows["transactional_legitimate"]["action"] == "promote"
    assert common_crawl_rows["instructional_legitimate"]["action"] == "adapt"
    assert common_crawl_rows["instructional_legitimate"]["current_count"] == 2
    assert common_crawl_rows["awareness_or_report"]["action"] == "adapt"
    assert common_crawl_rows["awareness_or_report"]["current_count"] == 1

    cert_rows = {row["key"]: row for row in sources["cert-fr-cti"]["rows"]}
    assert cert_rows["threat_intel"]["action"] == "extract_signals_only"
    assert cert_rows["synthetic_lure_candidate"]["action"] == "adapt"

    historical_rows = {
        row["key"]: row for row in sources["database-historical"]["rows"]
    }
    assert (
        historical_rows["historical_language_recheck_required"]["action"] == "archive"
    )
    assert historical_rows["historical_language_recheck_required"]["current_count"] == 2
    assert historical_rows["historical_repair_needed"]["action"] == "adapt"


def test_stage_two_routing_matrix_renders_markdown() -> None:
    markdown = StageTwoRoutingMatrixService.render_markdown(
        {
            "generated_at": "2026-04-07T00:00:00+00:00",
            "sources": [
                {
                    "source_name": "common-crawl-bigdata",
                    "route_summary": {"accepted": 1},
                    "subtype_summary": {"transactional_legitimate": 1},
                    "rejection_summary": {},
                    "rows": [
                        {
                            "key_type": "route_subtype",
                            "key": "transactional_legitimate",
                            "action": "promote",
                            "output_bucket": "promotion_queue",
                            "current_count": 1,
                            "adaptation_fit": "none",
                            "rationale": "ready for reviewed promotion",
                        }
                    ],
                }
            ],
        }
    )

    assert "# Stage-Two Routing Matrix" in markdown
    assert "common-crawl-bigdata" in markdown
    assert "transactional_legitimate" in markdown
