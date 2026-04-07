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
