from __future__ import annotations

from data_platform.services.shared.stage_two_reviewed_export import (
    StageTwoReviewedExportService,
)


def test_stage_two_reviewed_export_exports_usable_draft() -> None:
    service = StageTwoReviewedExportService()
    export_payload = service.build_export(
        {
            "drafts": [
                {
                    "draft_id": "draft-1",
                    "job_id": "job-1",
                    "raw_record_id": "raw-1",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "review_state": "usable",
                    "review_notes": [],
                    "quality_signals": {},
                    "full_text": "Objet : Information utile\n\nBonjour, merci de vérifier votre espace habituel en cas de doute.",
                },
                {
                    "draft_id": "draft-2",
                    "job_id": "job-2",
                    "raw_record_id": "raw-2",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "review_state": "needs_prompt_tuning",
                    "full_text": "Objet : Brouillon\n\nBonjour",
                },
            ]
        }
    )

    assert export_payload["exported_candidate_count"] == 1
    assert export_payload["skipped_state_summary"]["needs_prompt_tuning"] == 1
    candidate = export_payload["candidates"][0]
    assert candidate["label_id"] == 2
    assert candidate["corpus_row"]["label"] == 2
    assert candidate["corpus_row"]["language"] == "fr"
    assert candidate["redaction_status"] == "not_required"


def test_stage_two_reviewed_export_skips_duplicate_text_hashes() -> None:
    service = StageTwoReviewedExportService()
    export_payload = service.build_export(
        {
            "drafts": [
                {
                    "draft_id": "draft-a",
                    "job_id": "job-a",
                    "raw_record_id": "raw-a",
                    "source_name": "database-historical",
                    "rule_key": "historical_repair_needed",
                    "rewrite_mode": "repair_then_rewrite",
                    "target_label": "spam",
                    "review_state": "usable",
                    "full_text": "Objet : Bonus\n\nBonjour, profitez de cette offre aujourd'hui.",
                },
                {
                    "draft_id": "draft-b",
                    "job_id": "job-b",
                    "raw_record_id": "raw-b",
                    "source_name": "database-historical",
                    "rule_key": "historical_repair_needed",
                    "rewrite_mode": "repair_then_rewrite",
                    "target_label": "spam",
                    "review_state": "usable",
                    "full_text": "Objet : Bonus\n\nBonjour, profitez de cette offre aujourd'hui.",
                },
            ]
        }
    )

    assert export_payload["exported_candidate_count"] == 1
    assert export_payload["skipped_reason_summary"]["duplicate_text_sha256"] == 1


def test_stage_two_reviewed_export_render_markdown() -> None:
    markdown = StageTwoReviewedExportService.render_markdown(
        {
            "generated_at": "2026-04-07T00:00:00+00:00",
            "eligible_review_states": ["usable"],
            "exported_candidate_count": 1,
            "label_summary": {"spam": 1},
            "skipped_state_summary": {},
            "skipped_reason_summary": {},
            "candidates": [
                {
                    "candidate_id": "cand-1",
                    "source_name": "database-historical",
                    "raw_record_id": "raw-1",
                    "target_label": "spam",
                    "label_id": 1,
                    "review_state": "usable",
                    "text_length": 120,
                    "normalized_text": "Objet : Bonus\n\nBonjour",
                    "corpus_row": {
                        "archetype": "historical_repair_needed:repair_then_rewrite"
                    },
                }
            ],
        }
    )

    assert "# Stage-Two Reviewed Export" in markdown
    assert "cand-1" in markdown
    assert "Exported candidate count" in markdown


def test_stage_two_reviewed_export_skips_page_like_legitimate_subjects() -> None:
    service = StageTwoReviewedExportService()
    export_payload = service.build_export(
        {
            "drafts": [
                {
                    "draft_id": "draft-page-like",
                    "job_id": "job-page-like",
                    "raw_record_id": "raw-page-like",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "review_state": "usable",
                    "review_notes": ["page_like_legitimate_subject"],
                    "quality_signals": {"subject_page_like_hits": 1},
                    "full_text": "Objet : Point d'information pour selon les conditions générales\n\nBonjour, utilisez uniquement votre espace habituel.",
                }
            ]
        }
    )

    assert export_payload["exported_candidate_count"] == 0
    assert export_payload["skipped_reason_summary"]["page_like_legitimate_subject"] == 1


def test_stage_two_reviewed_export_skips_fragment_like_legitimate_subjects() -> None:
    service = StageTwoReviewedExportService()
    export_payload = service.build_export(
        {
            "drafts": [
                {
                    "draft_id": "draft-fragment-like",
                    "job_id": "job-fragment-like",
                    "raw_record_id": "raw-fragment-like",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "review_state": "usable",
                    "review_notes": ["fragment_like_legitimate_subject"],
                    "quality_signals": {},
                    "full_text": "Objet : Point d'information pour 15 €/min + prix de l'appel pour\n\nBonjour, utilisez uniquement votre espace habituel.",
                }
            ]
        }
    )

    assert export_payload["exported_candidate_count"] == 0
    assert (
        export_payload["skipped_reason_summary"]["fragment_like_legitimate_subject"]
        == 1
    )


def test_stage_two_reviewed_export_skips_subject_marker_without_review_note() -> None:
    service = StageTwoReviewedExportService()
    export_payload = service.build_export(
        {
            "drafts": [
                {
                    "draft_id": "draft-subject-leak",
                    "job_id": "job-subject-leak",
                    "raw_record_id": "raw-subject-leak",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "review_state": "usable",
                    "review_notes": [],
                    "quality_signals": {},
                    "full_text": "Objet : Conseils de sécurité pour conformément à cette dernière exigence réglementaire\n\nBonjour, vérifiez toujours vos demandes depuis votre espace habituel.",
                }
            ]
        }
    )

    assert export_payload["exported_candidate_count"] == 0
    assert export_payload["skipped_reason_summary"]["page_like_legitimate_subject"] == 1
