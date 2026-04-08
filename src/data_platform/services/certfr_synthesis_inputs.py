from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any


class CertFRSynthesisInputService:
    CHANNEL_KEYWORDS: dict[str, tuple[str, ...]] = {
        "email": ("courriel", "e-mail", "email", "phishing", "hameçonnage"),
        "sms": ("sms",),
        "imessage": ("imessage",),
        "web": ("site", "lien", "url", "domaine"),
    }
    FAMILY_LURE_MAP: dict[str, str] = {
        "dridex": "invoice or payment follow-up with an attachment or urgent action",
        "ta505": "document-sharing or urgent payment-themed lure",
        "emotet": "business communication that pushes the recipient to open a document quickly",
        "maze": "security incident or business continuity lure carrying high pressure",
        "ryuk": "urgent operational disruption lure that pushes fast response",
        "silence": "banking or financial institution themed lure",
        "generic": "urgent business-style lure with account or document verification",
    }
    THEME_LURE_MAP: dict[str, str] = {
        "phishing": "account confirmation or mailbox verification",
        "credential_theft": "login or password verification",
        "banking_malware": "payment, invoice, or banking workflow",
        "ransomware": "document, incident, or operational urgency that leads to execution",
        "generic_campaign": "urgent review of a business request",
    }
    THEME_LEXICAL_CUES: dict[str, tuple[str, ...]] = {
        "phishing": ("vérification", "accès", "compte", "confirmer"),
        "credential_theft": (
            "identifiants",
            "mot de passe",
            "connexion",
            "sécurité",
        ),
        "banking_malware": ("facture", "paiement", "virement", "document"),
        "ransomware": ("incident", "urgence", "document", "ouverture"),
        "generic_campaign": ("action requise", "consulter", "délai", "réponse"),
    }

    @classmethod
    def build_inputs(cls, signal_summary: dict[str, Any]) -> dict[str, Any]:
        grouped_samples: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(
            list
        )

        for sample in signal_summary.get("sampled_records", []):
            if sample.get("phishing_relevance") is not True:
                continue
            family = cls._resolve_primary_family(sample)
            theme = cls._resolve_primary_theme(sample)
            channel = cls._resolve_channel(sample)
            grouped_samples[(family, theme, channel)].append(sample)

        scenarios = [
            cls._build_scenario(
                family=family,
                theme=theme,
                channel=channel,
                samples=samples,
            )
            for (family, theme, channel), samples in sorted(grouped_samples.items())
        ]

        return {
            "mode": "certfr_synthesis_inputs",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "phishing_relevant_sampled_count": int(
                signal_summary.get("phishing_relevant_sampled_count", 0)
            ),
            "scenario_count": len(scenarios),
            "family_summary": dict(
                Counter(scenario["attack_family"] for scenario in scenarios)
            ),
            "theme_summary": dict(
                Counter(scenario["primary_theme"] for scenario in scenarios)
            ),
            "channel_summary": dict(
                Counter(scenario["delivery_channel"] for scenario in scenarios)
            ),
            "scenarios": scenarios,
        }

    @staticmethod
    def render_markdown(payload: dict[str, Any]) -> str:
        lines = [
            "# CERT-FR Synthesis Inputs",
            "",
            f"- Generated at: {payload.get('generated_at')}",
            f"- Phishing-relevant sampled count: {payload.get('phishing_relevant_sampled_count')}",
            f"- Scenario count: {payload.get('scenario_count')}",
            f"- Family summary: {payload.get('family_summary')}",
            f"- Theme summary: {payload.get('theme_summary')}",
            f"- Channel summary: {payload.get('channel_summary')}",
            "",
        ]

        for scenario in payload.get("scenarios", []):
            lines.extend(
                [
                    f"## {scenario['scenario_id']}",
                    "",
                    f"- Family: {scenario['attack_family']}",
                    f"- Theme: {scenario['primary_theme']}",
                    f"- Channel: {scenario['delivery_channel']}",
                    f"- Sample count: {scenario['sample_count']}",
                    f"- Lure focus: {scenario['lure_focus']}",
                    f"- Lexical cues: {', '.join(scenario.get('lexical_cues', []))}",
                    "",
                    "### Prompt Brief",
                    "",
                    scenario["prompt_brief"],
                    "",
                ]
            )
        return "\n".join(lines)

    @classmethod
    def _build_scenario(
        cls,
        *,
        family: str,
        theme: str,
        channel: str,
        samples: list[dict[str, Any]],
    ) -> dict[str, Any]:
        scenario_id = f"certfr-synth:{family}:{theme}:{channel}"
        lure_focus = cls._resolve_lure_focus(family, theme)
        lexical_cues = list(
            cls.THEME_LEXICAL_CUES.get(
                theme, cls.THEME_LEXICAL_CUES["generic_campaign"]
            )
        )
        prompt_brief = cls._build_prompt_brief(
            family=family,
            theme=theme,
            channel=channel,
            lure_focus=lure_focus,
            lexical_cues=lexical_cues,
        )

        return {
            "scenario_id": scenario_id,
            "attack_family": family,
            "primary_theme": theme,
            "delivery_channel": channel,
            "sample_count": len(samples),
            "sampled_record_ids": [sample.get("raw_record_id") for sample in samples],
            "seed_preview_examples": [
                str(sample.get("normalized_preview") or "")[:240]
                for sample in samples[:3]
            ],
            "ioc_enriched_record_ids": [
                sample.get("raw_record_id")
                for sample in samples
                if sum(
                    int(value) for value in (sample.get("ioc_counts") or {}).values()
                )
                > 0
            ],
            "lure_focus": lure_focus,
            "lexical_cues": lexical_cues,
            "generation_constraints": [
                "write the output in French",
                "shape the output as an inbox-style phishing email",
                "do not copy report wording verbatim",
                "do not include exact IOCs, domains, IPs, or hashes from the source material",
                "keep the message realistic and concise",
            ],
            "prompt_brief": prompt_brief,
        }

    @classmethod
    def _build_prompt_brief(
        cls,
        *,
        family: str,
        theme: str,
        channel: str,
        lure_focus: str,
        lexical_cues: list[str],
    ) -> str:
        return (
            "Rédige un e-mail de phishing réaliste en français inspiré de signaux CERT-FR. "
            f"La campagne de référence est liée à la famille {family}, avec un thème principal {theme} "
            f"et un canal de livraison prioritaire {channel}. "
            f"Le leurre doit ressembler à {lure_focus}. "
            f"Le texte doit intégrer naturellement des indices lexicaux comme {', '.join(lexical_cues)}. "
            "Le message doit rester plausible, urgent sans excès, et ne jamais réutiliser d'IOC exacts issus des rapports."
        )

    @classmethod
    def _resolve_primary_family(cls, sample: dict[str, Any]) -> str:
        families = sample.get("families") or []
        if families:
            return str(families[0])
        return "generic"

    @classmethod
    def _resolve_primary_theme(cls, sample: dict[str, Any]) -> str:
        themes = sample.get("themes") or []
        if themes:
            return str(themes[0])
        preview = str(sample.get("normalized_preview") or "").lower()
        if any(keyword in preview for keyword in ("phishing", "hameçonnage")):
            return "phishing"
        if any(
            keyword in preview
            for keyword in ("identifiant", "mot de passe", "credential")
        ):
            return "credential_theft"
        return "generic_campaign"

    @classmethod
    def _resolve_channel(cls, sample: dict[str, Any]) -> str:
        preview = str(sample.get("normalized_preview") or "").lower()
        for channel, keywords in cls.CHANNEL_KEYWORDS.items():
            if any(keyword in preview for keyword in keywords):
                return channel
        return "email"

    @classmethod
    def _resolve_lure_focus(cls, family: str, theme: str) -> str:
        if theme in cls.THEME_LURE_MAP:
            return cls.THEME_LURE_MAP[theme]
        return cls.FAMILY_LURE_MAP.get(family, cls.FAMILY_LURE_MAP["generic"])
