from __future__ import annotations

from data_platform.services.certfr_synthesis_inputs import (
    CertFRSynthesisInputService,
)


def test_certfr_synthesis_inputs_groups_phishing_relevant_samples() -> None:
    payload = CertFRSynthesisInputService.build_inputs(
        {
            "phishing_relevant_sampled_count": 2,
            "sampled_records": [
                {
                    "raw_record_id": "a",
                    "normalized_preview": "Campagne de phishing par courriel liée à Dridex",
                    "phishing_relevance": True,
                    "ioc_counts": {"domains": 0, "emails": 0, "ips": 0, "hashes": 0},
                    "families": ["dridex"],
                    "themes": ["banking_malware"],
                },
                {
                    "raw_record_id": "b",
                    "normalized_preview": "Campagne de phishing par courriel liée à Dridex",
                    "phishing_relevance": True,
                    "ioc_counts": {"domains": 0, "emails": 0, "ips": 1, "hashes": 0},
                    "families": ["dridex"],
                    "themes": ["banking_malware"],
                },
                {
                    "raw_record_id": "c",
                    "normalized_preview": "Rapport général sans campagne de phishing",
                    "phishing_relevance": False,
                    "ioc_counts": {"domains": 0, "emails": 0, "ips": 0, "hashes": 0},
                    "families": [],
                    "themes": [],
                },
            ],
        }
    )

    assert payload["scenario_count"] == 1
    scenario = payload["scenarios"][0]
    assert scenario["attack_family"] == "dridex"
    assert scenario["primary_theme"] == "banking_malware"
    assert scenario["delivery_channel"] == "email"
    assert scenario["sample_count"] == 2
    assert scenario["ioc_enriched_record_ids"] == ["b"]
    assert "dridex" in scenario["prompt_brief"].lower()


def test_certfr_synthesis_inputs_defaults_theme_and_channel() -> None:
    payload = CertFRSynthesisInputService.build_inputs(
        {
            "phishing_relevant_sampled_count": 1,
            "sampled_records": [
                {
                    "raw_record_id": "x",
                    "normalized_preview": "Campagne d'hameçonnage ciblée contre des comptes professionnels",
                    "phishing_relevance": True,
                    "ioc_counts": {"domains": 0, "emails": 0, "ips": 0, "hashes": 0},
                    "families": [],
                    "themes": [],
                }
            ],
        }
    )

    scenario = payload["scenarios"][0]
    assert scenario["attack_family"] == "generic"
    assert scenario["primary_theme"] == "phishing"
    assert scenario["delivery_channel"] == "email"


def test_certfr_synthesis_inputs_render_markdown() -> None:
    markdown = CertFRSynthesisInputService.render_markdown(
        {
            "generated_at": "2026-04-08T00:00:00+00:00",
            "phishing_relevant_sampled_count": 2,
            "scenario_count": 1,
            "family_summary": {"dridex": 1},
            "theme_summary": {"banking_malware": 1},
            "channel_summary": {"email": 1},
            "scenarios": [
                {
                    "scenario_id": "certfr-synth:dridex:banking_malware:email",
                    "attack_family": "dridex",
                    "primary_theme": "banking_malware",
                    "delivery_channel": "email",
                    "sample_count": 2,
                    "lure_focus": "invoice lure",
                    "lexical_cues": ["facture"],
                    "prompt_brief": "Rédige un e-mail de phishing réaliste en français.",
                }
            ],
        }
    )

    assert "# CERT-FR Synthesis Inputs" in markdown
    assert "certfr-synth:dridex:banking_malware:email" in markdown
    assert "Scenario count" in markdown
