from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any


class CertFRSignalSummaryService:
    FAMILY_KEYWORDS: dict[str, tuple[str, ...]] = {
        "maze": ("maze",),
        "silence": ("silence",),
        "dridex": ("dridex",),
        "ta505": ("ta505",),
        "ryuk": ("ryuk",),
        "emotet": ("emotet",),
        "qakbot": ("qakbot", "qbot"),
        "trickbot": ("trickbot",),
    }
    THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
        "ransomware": ("rançongiciel", "ransomware"),
        "banking_malware": ("dridex", "banque", "banking", "qakbot", "trickbot"),
        "phishing": ("phishing", "hameçonnage", "hameconnage"),
        "social_engineering": ("ingénierie sociale", "social engineering"),
        "credential_theft": ("identifiant", "mot de passe", "credential", "compte"),
    }
    CHANNEL_KEYWORDS: dict[str, tuple[str, ...]] = {
        "email": ("courriel", "e-mail", "email"),
        "sms": ("sms", "message"),
        "imessage": ("imessage",),
        "web": ("site", "lien", "url", "domaine"),
    }

    @classmethod
    def build_summary(cls, signal_bank: dict[str, Any]) -> dict[str, Any]:
        threat_intel_rule = cls._find_rule(signal_bank, "cert-fr-cti", "threat_intel")
        procedural_rule = cls._find_rule(
            signal_bank,
            "cert-fr-cti",
            "procedural_notification",
        )

        threat_samples = (
            threat_intel_rule.get("sampled_records", []) if threat_intel_rule else []
        )
        procedural_samples = (
            procedural_rule.get("sampled_records", []) if procedural_rule else []
        )

        family_counts = cls._count_keywords(threat_samples, cls.FAMILY_KEYWORDS)
        theme_counts = cls._count_keywords(threat_samples, cls.THEME_KEYWORDS)
        channel_counts = cls._count_keywords(
            threat_samples + procedural_samples,
            cls.CHANNEL_KEYWORDS,
        )
        ioc_totals = cls._count_iocs(threat_samples)
        phishing_relevant = len(
            [
                sample
                for sample in threat_samples
                if (sample.get("derived_payload") or {}).get("phishing_relevance")
                is True
            ]
        )

        return {
            "mode": "certfr_signal_summary",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "threat_intel_total_count": int(
                threat_intel_rule.get("current_count", 0) if threat_intel_rule else 0
            ),
            "sampled_threat_intel_count": len(threat_samples),
            "sampled_procedural_count": len(procedural_samples),
            "phishing_relevant_sampled_count": phishing_relevant,
            "ioc_totals": ioc_totals,
            "family_counts": dict(family_counts),
            "theme_counts": dict(theme_counts),
            "channel_counts": dict(channel_counts),
            "ioc_enriched_record_ids": [
                sample.get("raw_record_id")
                for sample in threat_samples
                if cls._sample_ioc_total(sample) > 0
            ],
            "sampled_records": [
                {
                    "raw_record_id": sample.get("raw_record_id"),
                    "normalized_preview": sample.get("normalized_preview"),
                    "phishing_relevance": (sample.get("derived_payload") or {}).get(
                        "phishing_relevance"
                    ),
                    "ioc_counts": (sample.get("derived_payload") or {}).get(
                        "ioc_counts", {}
                    ),
                    "families": cls._match_keywords(
                        str(sample.get("normalized_preview") or ""),
                        cls.FAMILY_KEYWORDS,
                    ),
                    "themes": cls._match_keywords(
                        str(sample.get("normalized_preview") or ""),
                        cls.THEME_KEYWORDS,
                    ),
                }
                for sample in threat_samples
            ],
        }

    @staticmethod
    def render_markdown(summary: dict[str, Any]) -> str:
        lines = [
            "# CERT-FR Signal Summary",
            "",
            f"- Generated at: {summary.get('generated_at')}",
            f"- Threat-intel total count: {summary.get('threat_intel_total_count')}",
            f"- Sampled threat-intel count: {summary.get('sampled_threat_intel_count')}",
            f"- Sampled procedural count: {summary.get('sampled_procedural_count')}",
            f"- Phishing-relevant sampled count: {summary.get('phishing_relevant_sampled_count')}",
            f"- IOC totals: {summary.get('ioc_totals')}",
            f"- Family counts: {summary.get('family_counts')}",
            f"- Theme counts: {summary.get('theme_counts')}",
            f"- Channel counts: {summary.get('channel_counts')}",
            "",
        ]
        return "\n".join(lines)

    @staticmethod
    def _find_rule(
        signal_bank: dict[str, Any], source_name: str, key: str
    ) -> dict[str, Any] | None:
        for source in signal_bank.get("sources", []):
            if source.get("source_name") != source_name:
                continue
            for rule in source.get("rules", []):
                if rule.get("key") == key:
                    return rule
        return None

    @classmethod
    def _count_keywords(
        cls,
        samples: list[dict[str, Any]],
        keyword_map: dict[str, tuple[str, ...]],
    ) -> Counter[str]:
        counts: Counter[str] = Counter()
        for sample in samples:
            preview = str(sample.get("normalized_preview") or "")
            for name in cls._match_keywords(preview, keyword_map):
                counts[name] += 1
        return counts

    @staticmethod
    def _match_keywords(
        text: str, keyword_map: dict[str, tuple[str, ...]]
    ) -> list[str]:
        lowered = text.lower()
        return [
            name
            for name, keywords in keyword_map.items()
            if any(re.search(re.escape(keyword), lowered) for keyword in keywords)
        ]

    @classmethod
    def _count_iocs(cls, samples: list[dict[str, Any]]) -> dict[str, int]:
        totals: Counter[str] = Counter()
        for sample in samples:
            for key, value in (
                (sample.get("derived_payload") or {}).get("ioc_counts") or {}
            ).items():
                totals[key] += int(value)
        return dict(totals)

    @staticmethod
    def _sample_ioc_total(sample: dict[str, Any]) -> int:
        ioc_counts = (sample.get("derived_payload") or {}).get("ioc_counts") or {}
        return sum(int(value) for value in ioc_counts.values())
