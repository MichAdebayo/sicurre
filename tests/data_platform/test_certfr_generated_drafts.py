from __future__ import annotations

import pytest

from data_platform.services.certfr_generated_drafts import CertFRGeneratedDraftService


def test_certfr_generated_drafts_builds_banking_phishing_email() -> None:
    payload = CertFRGeneratedDraftService.build_drafts(
        {
            "scenarios": [
                {
                    "scenario_id": "certfr-synth:dridex:banking_malware:email",
                    "attack_family": "dridex",
                    "primary_theme": "banking_malware",
                    "delivery_channel": "email",
                    "sampled_record_ids": ["a"],
                    "prompt_brief": "Prompt brief here",
                }
            ]
        }
    )

    assert payload["draft_count"] == 1
    draft = payload["drafts"][0]
    assert draft["target_label"] == "phishing"
    assert draft["review_state"] == "usable"
    assert "paiement" in draft["body"].lower() or "facture" in draft["body"].lower()
    assert "[LIEN_" in draft["body"]
    assert draft["quality_signals"]["cta_present"] is True
    assert draft["quality_signals"]["structure_opening"]
    assert draft["quality_signals"]["structure_context"]
    assert draft["quality_signals"]["structure_pressure"]
    assert draft["quality_signals"]["cta_position"] in {
        "after_opening",
        "after_context",
        "append_opening",
        "prepend_pressure",
    }


def test_certfr_generated_drafts_downgrades_duplicate_outputs() -> None:
    drafts = [
        {
            "text_sha256": "same-hash",
            "review_state": "usable",
            "review_notes": [],
        },
        {
            "text_sha256": "same-hash",
            "review_state": "usable",
            "review_notes": [],
        },
    ]

    CertFRGeneratedDraftService._apply_duplicate_review_flags(drafts)

    assert all(draft["review_state"] == "needs_prompt_tuning" for draft in drafts)
    assert all("duplicate_generated_draft" in draft["review_notes"] for draft in drafts)


def test_certfr_generated_drafts_render_markdown() -> None:
    markdown = CertFRGeneratedDraftService.render_markdown(
        {
            "generated_at": "2026-04-08T00:00:00+00:00",
            "draft_count": 1,
            "review_summary": {"usable": 1},
            "theme_summary": {"phishing": 1},
            "family_summary": {"generic": 1},
            "cta_position_summary": {"after_context": 1},
            "drafts": [
                {
                    "draft_id": "draft-1",
                    "scenario_id": "scenario-1",
                    "attack_family": "generic",
                    "primary_theme": "phishing",
                    "delivery_channel": "email",
                    "review_state": "usable",
                    "review_notes": [],
                    "quality_signals": {
                        "phishing_cue_hits": 4,
                        "cta_position": "after_context",
                    },
                    "subject": "Sujet",
                    "body": "Bonjour",
                }
            ],
        }
    )

    assert "# CERT-FR Generated Drafts" in markdown
    assert "scenario-1" in markdown
    assert "Review summary" in markdown
    assert "CTA position" in markdown


def test_certfr_generated_drafts_flags_missing_cta() -> None:
    review_state, review_notes, quality_signals = (
        CertFRGeneratedDraftService._assess_draft(
            scenario={"prompt_brief": "brief"},
            subject="Sujet",
            body="Bonjour, merci de confirmer votre accès aujourd'hui.",
            full_text="Objet : Sujet\n\nBonjour, merci de confirmer votre accès aujourd'hui.",
        )
    )

    assert review_state == "needs_prompt_tuning"
    assert "missing_action_cta" in review_notes
    assert quality_signals["cta_present"] is False


def test_certfr_generated_drafts_varies_cta_by_scenario() -> None:
    payload = CertFRGeneratedDraftService.build_drafts(
        {
            "scenarios": [
                {
                    "scenario_id": "certfr-synth:generic:generic_campaign:email-a",
                    "attack_family": "generic",
                    "primary_theme": "generic_campaign",
                    "delivery_channel": "email",
                    "sampled_record_ids": ["a"],
                    "prompt_brief": "brief a",
                },
                {
                    "scenario_id": "certfr-synth:generic:generic_campaign:email-b",
                    "attack_family": "generic",
                    "primary_theme": "generic_campaign",
                    "delivery_channel": "email",
                    "sampled_record_ids": ["b"],
                    "prompt_brief": "brief b",
                },
                {
                    "scenario_id": "certfr-synth:generic:generic_campaign:email-c",
                    "attack_family": "generic",
                    "primary_theme": "generic_campaign",
                    "delivery_channel": "email",
                    "sampled_record_ids": ["c"],
                    "prompt_brief": "brief c",
                },
            ]
        }
    )

    cta_positions = {
        draft["quality_signals"]["cta_position"] for draft in payload["drafts"]
    }
    bodies = {draft["body"] for draft in payload["drafts"]}
    opening_variants = {
        draft["quality_signals"]["structure_opening"] for draft in payload["drafts"]
    }
    context_variants = {
        draft["quality_signals"]["structure_context"] for draft in payload["drafts"]
    }
    pressure_variants = {
        draft["quality_signals"]["structure_pressure"] for draft in payload["drafts"]
    }

    assert len(cta_positions) >= 2
    assert len(bodies) >= 2
    assert len(opening_variants) >= 2
    assert len(context_variants) >= 2
    assert len(pressure_variants) >= 2


def test_certfr_generated_drafts_varies_by_variant_index() -> None:
    payload = CertFRGeneratedDraftService.build_drafts(
        {
            "scenarios": [
                {
                    "scenario_id": "certfr-synth:generic:credential_theft:email",
                    "attack_family": "generic",
                    "primary_theme": "credential_theft",
                    "delivery_channel": "email",
                    "sampled_record_ids": ["a"],
                    "prompt_brief": "brief a",
                    "variant_index": 0,
                },
                {
                    "scenario_id": "certfr-synth:generic:credential_theft:email",
                    "attack_family": "generic",
                    "primary_theme": "credential_theft",
                    "delivery_channel": "email",
                    "sampled_record_ids": ["a"],
                    "prompt_brief": "brief a",
                    "variant_index": 1,
                },
                {
                    "scenario_id": "certfr-synth:generic:credential_theft:email",
                    "attack_family": "generic",
                    "primary_theme": "credential_theft",
                    "delivery_channel": "email",
                    "sampled_record_ids": ["a"],
                    "prompt_brief": "brief a",
                    "variant_index": 2,
                },
            ]
        }
    )

    variant_indexes = [draft["variant_index"] for draft in payload["drafts"]]
    bodies = {draft["body"] for draft in payload["drafts"]}

    assert variant_indexes == [0, 1, 2]
    assert len(bodies) >= 2


@pytest.mark.parametrize(
    ("scenario_id", "attack_family", "primary_theme"),
    [
        ("certfr-synth:dridex:banking_malware:email", "dridex", "banking_malware"),
        ("certfr-synth:emotet:generic_campaign:email", "emotet", "generic_campaign"),
        ("certfr-synth:generic:phishing:email", "generic", "phishing"),
        ("certfr-synth:generic:ransomware:email", "generic", "ransomware"),
        ("certfr-synth:maze:ransomware:email", "maze", "ransomware"),
        ("certfr-synth:ryuk:ransomware:email", "ryuk", "ransomware"),
        ("certfr-synth:generic:credential_theft:email", "generic", "credential_theft"),
        ("certfr-synth:generic:generic_campaign:email", "generic", "generic_campaign"),
        ("certfr-synth:ta505:generic_campaign:email", "ta505", "generic_campaign"),
    ],
)
def test_certfr_generated_drafts_weak_families_remain_usable_across_16_variants(
    scenario_id: str,
    attack_family: str,
    primary_theme: str,
) -> None:
    payload = CertFRGeneratedDraftService.build_drafts(
        {
            "scenarios": [
                {
                    "scenario_id": scenario_id,
                    "attack_family": attack_family,
                    "primary_theme": primary_theme,
                    "delivery_channel": "email",
                    "sampled_record_ids": ["a"],
                    "prompt_brief": "brief a",
                    "variant_index": variant_index,
                }
                for variant_index in range(16)
            ]
        }
    )

    assert payload["review_summary"] == {"usable": 16}
