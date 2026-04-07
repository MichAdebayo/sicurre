from __future__ import annotations

from data_platform.services.stage_two_rewrite_jobs import StageTwoRewriteJobService


def test_stage_two_rewrite_jobs_builds_prompt_ready_jobs() -> None:
    jobs = StageTwoRewriteJobService.build_jobs(
        {
            "sources": [
                {
                    "source_name": "common-crawl-bigdata",
                    "rules": [
                        {
                            "key": "instructional_legitimate",
                            "adaptation_fit": "high",
                            "rationale": "rewrite page into notification",
                            "label_summary": {"legitimate": 2},
                            "sampled_records": [
                                {
                                    "raw_record_id": "abc",
                                    "extracted_label": "legitimate",
                                    "normalized_preview": "Veuillez verifier vos informations",
                                    "normalized_length": 120,
                                    "similarity_score": 0.3,
                                    "trace_summary": "trace",
                                    "derived_payload": {
                                        "marker_evidence": {"delivery_hits": 2}
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    )

    assert jobs["job_count"] == 1
    job = jobs["jobs"][0]
    assert job["target_label"] == "legitimate"
    assert job["rewrite_mode"] == "institutional_page_to_notification"
    assert "retain service-notification delivery wording" in job["prompt_hints"]


def test_stage_two_rewrite_jobs_render_markdown() -> None:
    markdown = StageTwoRewriteJobService.render_markdown(
        {
            "generated_at": "2026-04-07T00:00:00+00:00",
            "job_count": 1,
            "jobs": [
                {
                    "job_id": "job-1",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "adaptation_fit": "high",
                    "raw_record_id": "abc",
                    "constraints": ["keep the text in French"],
                    "prompt_hints": ["retain service-notification delivery wording"],
                    "source_preview": "preview",
                }
            ],
        }
    )

    assert "# Stage-Two Rewrite Jobs" in markdown
    assert "job-1" in markdown
