from __future__ import annotations

import pytest

from data_platform.services.llm_generation_feasibility import (
    LLMGenerationFeasibilityService,
    OpenAICompatibleInferenceClient,
)


def test_adapted_prompt_avoids_explicit_phishing_wording() -> None:
    system_prompt, user_prompt = LLMGenerationFeasibilityService.build_adapted_prompts(
        seed_text="Urgent account confirmation required.",
        archetype="banque_securite",
        fr_entity="BNP Paribas",
        references=[
            {
                "normalized_text": "Objet : Vérification de sécurité\n\nBonjour,\n\n...",
            }
        ],
    )

    assert "phishing" not in system_prompt.lower()
    assert "phishing" not in user_prompt.lower()
    assert "Objet :" in user_prompt


def test_adapted_context_brief_prompt_avoids_raw_seed_dump() -> None:
    seed_text = (
        "Subject: Confidential partnership transfer\n\n"
        "I need your help to move 21 500 000 USD immediately. "
        "Reply today with your banking details."
    )
    system_prompt, user_prompt = (
        LLMGenerationFeasibilityService.build_adapted_context_brief_prompts(
            seed_text=seed_text,
            archetype="banque_securite",
            fr_entity="BNP Paribas",
            references=[
                {
                    "normalized_text": "Objet : Vérification de sécurité\n\nBonjour,\n\n...",
                }
            ],
        )
    )

    assert "phishing" not in system_prompt.lower()
    assert "phishing" not in user_prompt.lower()
    assert "translate" not in user_prompt.lower()
    assert "english seed" not in user_prompt.lower()
    assert "21 500 000 usd" not in user_prompt.lower()
    assert "Scenario focus:" in user_prompt
    assert "Requested user action:" in user_prompt
    assert "Objet :" in user_prompt


def test_adapted_context_brief_prompt_includes_archetype_hard_constraints() -> None:
    _, user_prompt = (
        LLMGenerationFeasibilityService.build_adapted_context_brief_prompts(
            seed_text="Urgent bank verification required.",
            archetype="banque_securite",
            fr_entity="BNP Paribas",
            references=[],
        )
    )

    assert "Hard scenario constraints:" in user_prompt
    assert "3D Secure verification issue" in user_prompt
    assert "Do not ask the reader to open an attachment" in user_prompt
    assert "Respect every hard scenario constraint above" in user_prompt


def test_explicit_phishing_context_is_opt_in() -> None:
    system_prompt, user_prompt = (
        LLMGenerationFeasibilityService.build_adapted_context_brief_prompts(
            seed_text="Urgent bank verification required.",
            archetype="banque_securite",
            fr_entity="BNP Paribas",
            references=[],
            prompt_context_mode="explicit_phishing",
        )
    )

    assert "phishing-simulation" in system_prompt.lower()
    assert "offline classifier evaluation" in system_prompt.lower()
    assert "phishing" not in user_prompt.lower()


def test_certfr_prompt_avoids_report_language_and_explicit_phishing_wording() -> None:
    system_prompt, user_prompt = (
        LLMGenerationFeasibilityService.build_certfr_synthetic_prompts(
            scenario={
                "attack_family": "emotet",
                "primary_theme": "generic_campaign",
                "delivery_channel": "email",
                "lure_focus": "urgent review",
                "lexical_cues": ["action requise", "délai"],
            },
            references=[],
        )
    )

    assert "phishing" not in system_prompt.lower()
    assert "phishing" not in user_prompt.lower()
    assert "report" not in user_prompt.lower()
    assert "Objet :" in user_prompt


def test_openai_compatible_client_extracts_string_content() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "content": "Objet : Test\n\nBonjour,\n\nCeci est un test.",
                }
            }
        ]
    }

    assert (
        OpenAICompatibleInferenceClient._extract_content(payload)
        == "Objet : Test\n\nBonjour,\n\nCeci est un test."
    )


def test_openai_compatible_client_extracts_list_content() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "output_text", "text": "Objet : Test"},
                        {"type": "output_text", "text": "Bonjour"},
                    ],
                }
            }
        ]
    }

    assert (
        OpenAICompatibleInferenceClient._extract_content(payload)
        == "Objet : Test\nBonjour"
    )


def test_openai_compatible_client_raises_on_missing_choices() -> None:
    with pytest.raises(ValueError, match="choices"):
        OpenAICompatibleInferenceClient._extract_content({})
