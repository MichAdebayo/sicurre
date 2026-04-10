from __future__ import annotations

from data_platform.services.generation_staging import GenerationStagingService


def test_generation_staging_builds_bundle_counts() -> None:
    bundle = GenerationStagingService.build_bundle(
        generator_name="common_crawl_signal_synthetic",
        source_name="common-crawl-bigdata",
        parent_source="common-crawl-bigdata",
        samples=[
            {
                "draft_id": "draft-1",
                "variant_index": 0,
                "source_name": "common-crawl-bigdata",
                "parent_source": "common-crawl-bigdata",
                "target_label": "phishing",
                "primary_theme": "delivery",
                "review_state": "usable",
                "review_notes": [],
                "text_sha256": "hash-1",
                "nearest_reference_raw_record_id": "raw-1",
                "nearest_similarity": 1.0,
            },
            {
                "draft_id": "draft-2",
                "variant_index": 0,
                "source_name": "common-crawl-bigdata",
                "parent_source": "common-crawl-bigdata",
                "target_label": "phishing",
                "primary_theme": "security",
                "review_state": "needs_prompt_tuning",
                "review_notes": ["weak_target_alignment"],
                "text_sha256": "hash-2",
                "nearest_reference_raw_record_id": "raw-2",
                "nearest_similarity": 0.91,
            },
        ],
    )

    assert bundle["run"]["total_draft_count"] == 2
    assert bundle["run"]["usable_draft_count"] == 1
    assert bundle["run"]["needs_prompt_tuning_count"] == 1
    assert bundle["sample_count"] == 2


def test_generation_staging_render_markdown() -> None:
    bundle = {
        "run": {
            "generator_name": "adapted_phishing",
            "source_name": "enron_spam",
            "parent_source": "enron_spam",
            "status": "completed",
            "total_draft_count": 1,
            "usable_draft_count": 1,
            "needs_prompt_tuning_count": 0,
            "dropped_draft_count": 0,
        },
        "samples": [
            {
                "draft_id": "draft-1",
                "variant_index": 0,
                "target_label": "phishing",
                "review_state": "usable",
                "primary_theme": "tax_urgency",
                "review_notes": [],
                "nearest_reference_raw_record_id": "raw-1",
                "nearest_similarity": 0.88,
            }
        ],
    }

    markdown = GenerationStagingService.render_markdown(bundle)

    assert "No-Write Generation Bundle" in markdown
    assert "adapted_phishing" in markdown
    assert "draft-1" in markdown
