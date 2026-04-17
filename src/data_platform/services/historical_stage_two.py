from __future__ import annotations

import re
from typing import Any

from db.models.lineage import NormalizedLabel
from data_platform.services.database_source_naming import (
    database_source_family,
    database_source_leaf,
)
from data_platform.services.stage_two_models import StageTwoReviewResult


class HistoricalStageTwoService:
    FRENCH_HINTS = (
        "bonjour",
        "cordialement",
        "veuillez",
        "votre",
        "vous",
        "mise à jour",
        "compte",
        "service",
        "message",
        "gratuit",
        "offre",
        "merci",
        "cliquez",
        "connexion",
        "paiement",
    )
    NON_FRENCH_HINTS = (
        "register now",
        "unsubscribe",
        "welcome",
        "top stories",
        "free spins",
        "your account",
        "account-id",
        "you have received",
        "received a payment",
        "pending in your account",
        "protect your",
        "click here",
        "attenzione",
        "hai fatto",
        "ora tocca",
        "rispondere",
        "qualcuno",
        "tuo profilo",
        "rischio",
        "misteriosa donna",
        "приглашение",
    )
    MOJIBAKE_MARKERS = ("Ã", "Â", "вЂ", "рџ", "�")
    HTML_RESIDUE_MARKERS = (
        "<!doctype",
        "<style",
        "</title",
        "title>",
        "body{",
        "meta charset",
        "viewport",
        "http-equiv",
        "content-type",
        "translated-ltr",
        "xmlns=",
    )
    FOOTER_MARKERS = (
        "top stories of the day",
        "if you believe this has been sent to you in error",
        "please safely unsubscribe",
    )

    @staticmethod
    def _count_markers(text: str, markers: tuple[str, ...]) -> int:
        lowered_text = text.lower()
        return len([marker for marker in markers if marker in lowered_text])

    @staticmethod
    def get_source_path(raw_content: dict[str, Any]) -> str:
        return str(raw_content.get("source", "")).strip().lower()

    @classmethod
    def get_subsource(cls, raw_content: dict[str, Any]) -> str:
        return database_source_leaf(cls.get_source_path(raw_content))

    @classmethod
    def map_label(cls, raw_content: dict[str, Any]) -> NormalizedLabel | None:
        historical_source = cls.get_subsource(raw_content)
        if historical_source.startswith("synthetic_phishing"):
            return NormalizedLabel.PHISHING
        if historical_source == "adapted_en_fr":
            return NormalizedLabel.PHISHING
        if historical_source.startswith("crowdsourced_spam"):
            return NormalizedLabel.SPAM

        raw_label = raw_content.get("label")
        if raw_label in {1, "1", True, "phishing"}:
            return NormalizedLabel.PHISHING
        if raw_label in {0, "0", False, "legitimate", "ham"}:
            return NormalizedLabel.LEGITIMATE
        return None

    @classmethod
    def review(
        cls,
        cleaned_text: str,
        raw_content: dict[str, Any],
    ) -> StageTwoReviewResult:
        repaired_text, extraction_trace = cls._repair_text(cleaned_text)
        route_outcome, route_reason, route_trace = cls._route_candidate(
            repaired_text,
            raw_content,
        )
        return StageTwoReviewResult(
            extracted_text=repaired_text,
            route_outcome=route_outcome,
            route_reason=route_reason,
            route_subtype=None,
            extraction_trace=extraction_trace,
            route_trace=route_trace,
            derived_payload={
                "derived_type": "historical_stage_two_candidate",
                "historical_source_path": cls.get_source_path(raw_content) or None,
                "historical_source_family": database_source_family(
                    cls.get_source_path(raw_content)
                ),
                "historical_subsource": cls.get_subsource(raw_content) or None,
                "quality_gate_passed": route_outcome == "accepted",
                "route_reason": route_reason,
            },
        )

    @classmethod
    def _looks_corrupted_or_non_french(cls, text: str) -> tuple[bool, str | None]:
        mojibake_hits = sum(text.count(marker) for marker in cls.MOJIBAKE_MARKERS)
        french_hits = cls._count_markers(text, cls.FRENCH_HINTS)
        non_french_hits = cls._count_markers(text, cls.NON_FRENCH_HINTS)

        if re.search(r"[А-Яа-яЁё]", text):
            return True, "historical_language_recheck_required"
        if mojibake_hits >= 3:
            return True, "historical_repair_needed"
        if non_french_hits >= 2 and french_hits == 0:
            return True, "historical_language_recheck_required"
        return False, None

    @classmethod
    def _repair_text(cls, text: str) -> tuple[str, tuple[str, ...]]:
        repaired_text = text
        trace_steps: list[str] = []

        without_invisible = re.sub(
            r"[\u034f\u200b-\u200f\u2060\ufeff]+", "", repaired_text
        )
        if without_invisible != repaired_text:
            repaired_text = without_invisible
            trace_steps.append("historical_invisible_chars_removed")

        lower_repaired = repaired_text.lower()
        for marker in cls.FOOTER_MARKERS:
            marker_index = lower_repaired.find(marker)
            if marker_index != -1:
                repaired_text = repaired_text[:marker_index].strip()
                lower_repaired = repaired_text.lower()
                trace_steps.append("historical_footer_removed")
                break

        stripped_residue = repaired_text
        for marker in cls.HTML_RESIDUE_MARKERS:
            stripped_residue = re.sub(
                re.escape(marker),
                " ",
                stripped_residue,
                flags=re.IGNORECASE,
            )
        stripped_residue = re.sub(r"\s+", " ", stripped_residue).strip()
        if stripped_residue != repaired_text:
            repaired_text = stripped_residue
            trace_steps.append("historical_html_residue_removed")

        return repaired_text, tuple(trace_steps)

    @classmethod
    def _route_candidate(
        cls,
        text: str,
        raw_content: dict[str, Any],
    ) -> tuple[str, str | None, tuple[str, ...]]:
        trace_steps = ["historical_body_or_text_selected"]
        historical_source = cls.get_subsource(raw_content)
        if historical_source:
            trace_steps.append(f"historical_subsource:{historical_source}")

        needs_repair, route_reason = cls._looks_corrupted_or_non_french(text)
        if needs_repair:
            trace_steps.append("historical_quality_gate_failed")
            return "specialized_processing", route_reason, tuple(trace_steps)

        if (
            historical_source.startswith("crowdsourced_spam")
            and cls._count_markers(text, cls.FRENCH_HINTS) == 0
        ):
            trace_steps.append("historical_quality_gate_failed")
            return (
                "specialized_processing",
                "historical_language_recheck_required",
                tuple(trace_steps),
            )

        if historical_source.startswith("crowdsourced_spam") and len(text) < 80:
            trace_steps.append("historical_quality_gate_failed")
            return (
                "specialized_processing",
                "historical_content_too_thin",
                tuple(trace_steps),
            )

        if cls._count_markers(text, cls.HTML_RESIDUE_MARKERS) > 0:
            trace_steps.append("historical_quality_gate_failed")
            return (
                "specialized_processing",
                "historical_html_repair_required",
                tuple(trace_steps),
            )

        trace_steps.append("historical_quality_gate_passed")
        return "accepted", None, tuple(trace_steps)
