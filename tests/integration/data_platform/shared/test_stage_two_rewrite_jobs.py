from __future__ import annotations

from data_platform.services.shared.stage_two_rewrite_jobs import (
    StageTwoRewriteJobService,
)


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


def test_stage_two_rewrite_jobs_assigns_awareness_mode_and_hint() -> None:
    jobs = StageTwoRewriteJobService.build_jobs(
        {
            "sources": [
                {
                    "source_name": "common-crawl-bigdata",
                    "rules": [
                        {
                            "key": "awareness_or_report",
                            "adaptation_fit": "medium",
                            "rationale": "rewrite awareness page into warning notification",
                            "label_summary": {"legitimate": 1},
                            "sampled_records": [
                                {
                                    "raw_record_id": "aware-1",
                                    "extracted_label": "legitimate",
                                    "normalized_preview": "Comment reconnaître un appel frauduleux ? Ne divulguez jamais vos informations personnelles.",
                                    "normalized_length": 120,
                                    "similarity_score": 0.2,
                                    "trace_summary": "trace",
                                    "derived_payload": {
                                        "marker_evidence": {"awareness_hits": 1}
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    )

    job = jobs["jobs"][0]
    assert job["rewrite_mode"] == "awareness_page_to_warning_notification"
    assert "shape the output as a defensive vigilance reminder" in job["prompt_hints"]


def test_stage_two_rewrite_jobs_assigns_common_crawl_phishing_mode_and_hints() -> None:
    jobs = StageTwoRewriteJobService.build_jobs(
        {
            "sources": [
                {
                    "source_name": "common-crawl-bigdata",
                    "rules": [
                        {
                            "key": "phishing_lure_candidate",
                            "adaptation_fit": "high",
                            "rationale": "rewrite scam report into phishing example",
                            "label_summary": {"phishing": 1},
                            "sampled_records": [
                                {
                                    "raw_record_id": "phish-1",
                                    "extracted_label": "phishing",
                                    "normalized_preview": "Site internet frauduleux. Message reçu ce jour. Escroquerie au faux colis.",
                                    "normalized_length": 120,
                                    "similarity_score": 0.2,
                                    "trace_summary": "trace",
                                    "derived_payload": {
                                        "marker_evidence": {
                                            "phishing_report_hits": 2,
                                            "phishing_lure_hits": 2,
                                        }
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    )

    job = jobs["jobs"][0]
    assert job["target_label"] == "phishing"
    assert job["rewrite_mode"] == "embedded_lure_to_phishing_email"
    assert (
        "extract the embedded scam pretext from the report wording"
        in job["prompt_hints"]
    )
    assert "shape the output as a realistic phishing email" in job["prompt_hints"]


def test_stage_two_rewrite_jobs_canonicalize_database_child_sources() -> None:
    jobs = StageTwoRewriteJobService.build_jobs(
        {
            "sources": [
                {
                    "source_name": "database/faker/synthetic_phishing_medium",
                    "rules": [
                        {
                            "key": "historical_repair_needed",
                            "adaptation_fit": "medium",
                            "rationale": "repair before rewrite",
                            "label_summary": {"phishing": 1},
                            "sampled_records": [
                                {
                                    "raw_record_id": "db-1",
                                    "extracted_label": "phishing",
                                    "normalized_preview": "Votre compte nécessite une confirmation immédiate.",
                                    "normalized_length": 110,
                                    "similarity_score": 0.4,
                                    "trace_summary": "trace",
                                    "derived_payload": {},
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    )

    job = jobs["jobs"][0]
    assert job["rewrite_mode"] == "repair_then_rewrite"
    assert (
        "repair encoding and formatting corruption before rewriting"
        in job["constraints"]
    )
    assert "repair mojibake and strip residual HTML" in job["prompt_hints"]
