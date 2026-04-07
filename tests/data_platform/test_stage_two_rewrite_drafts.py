from __future__ import annotations

from data_platform.services.stage_two_rewrite_drafts import StageTwoRewriteDraftService


def test_stage_two_rewrite_drafts_builds_usable_legitimate_notification() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-1",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "abc",
                    "source_preview": "A réception de mail, de sms ou d'appels douteux, ne renseignez jamais vos données bancaires et personnelles.",
                }
            ]
        }
    )

    assert drafts["draft_count"] == 1
    draft = drafts["drafts"][0]
    assert draft["review_state"] == "usable"
    assert "Bonjour" in draft["body"]
    assert "service client" in draft["body"].lower()


def test_stage_two_rewrite_drafts_builds_french_repaired_spam() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-2",
                    "source_name": "database-historical",
                    "rule_key": "historical_repair_needed",
                    "rewrite_mode": "repair_then_rewrite",
                    "target_label": "spam",
                    "raw_record_id": "hist-1",
                    "source_preview": "Objet : WELCOME BONUS 2000€ + 100 FREE SPINS Pending in your Account",
                }
            ]
        }
    )

    draft = drafts["drafts"][0]
    assert draft["review_state"] == "usable"
    assert "2000 €" in draft["subject"]
    assert "100 tours gratuits" in draft["body"]


def test_stage_two_rewrite_drafts_marks_empty_source_as_drop() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-3",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "empty-1",
                    "source_preview": "",
                }
            ]
        }
    )

    draft = drafts["drafts"][0]
    assert draft["review_state"] == "drop"
    assert "insufficient_source_context" in draft["review_notes"]


def test_stage_two_rewrite_drafts_downgrades_duplicate_outputs() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-a",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "dup-a",
                    "source_preview": "Veuillez sécuriser votre accès à votre compte dès aujourd'hui.",
                },
                {
                    "job_id": "job-b",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "dup-b",
                    "source_preview": "Veuillez sécuriser votre accès à votre compte dès aujourd'hui.",
                },
            ]
        }
    )

    for draft in drafts["drafts"]:
        assert draft["review_state"] == "needs_prompt_tuning"
        assert "duplicate_generated_draft" in draft["review_notes"]


def test_stage_two_rewrite_drafts_render_markdown() -> None:
    markdown = StageTwoRewriteDraftService.render_markdown(
        {
            "generated_at": "2026-04-07T00:00:00+00:00",
            "draft_count": 1,
            "review_summary": {"usable": 1},
            "target_label_summary": {"legitimate": 1},
            "drafts": [
                {
                    "draft_id": "draft-1",
                    "job_id": "job-1",
                    "source_name": "common-crawl-bigdata",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "review_state": "usable",
                    "review_notes": [],
                    "quality_signals": {"french_marker_count": 4},
                    "subject": "Sujet",
                    "body": "Bonjour",
                }
            ],
        }
    )

    assert "# Stage-Two Rewrite Drafts" in markdown
    assert "draft-1" in markdown
    assert "Review summary" in markdown
