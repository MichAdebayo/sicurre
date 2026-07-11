from __future__ import annotations

import re
from typing import Any

from data_platform.extractors.certfr_cti import CertFRCtiExtractor
from data_platform.services.shared.stage_two_models import StageTwoReviewResult


class CertFRStageTwoService:
    NOTIFICATION_MARKERS = (
        "notification",
        "courriel d'alerte",
        "courriel de notification",
        "imessage",
        "sms",
        "threat-notifications",
        "email.apple.com",
        "apple.com",
    )
    REPORT_MARKERS = (
        "panorama de la cybermenace",
        "tlp:clear",
        "table des matières",
        "contents",
        "nombredepages",
        "numberofpages",
        "premier ministre",
        "anssi",
        "certfr-",
        "affaire suivie par",
    )
    EMBEDDED_MESSAGE_MARKERS = (
        "bonjour",
        "bonsoir",
        "madame",
        "monsieur",
        "veuillez",
        "cliquez",
        "votre compte",
        "objet:",
    )

    @classmethod
    def review(
        cls,
        cleaned_text: str,
        raw_content: dict[str, Any],
    ) -> StageTwoReviewResult:
        extracted_text, extraction_trace = cls._extract_window(cleaned_text)
        route_outcome, route_reason, route_subtype, route_trace = cls._route_candidate(
            extracted_text
        )
        derived_payload = cls._build_derived_payload(
            extracted_text=extracted_text,
            raw_content=raw_content,
            route_subtype=route_subtype,
            route_reason=route_reason,
        )
        return StageTwoReviewResult(
            extracted_text=extracted_text,
            route_outcome=route_outcome,
            route_reason=route_reason,
            route_subtype=route_subtype,
            extraction_trace=extraction_trace,
            route_trace=route_trace,
            derived_payload=derived_payload,
        )

    @staticmethod
    def _count_markers(text: str, markers: tuple[str, ...]) -> int:
        lowered_text = text.lower()
        return len([marker for marker in markers if marker in lowered_text])

    @staticmethod
    def _split_candidate_segments(text: str) -> list[str]:
        segments = [
            segment.strip()
            for segment in re.split(r"(?<=[.!?])\s+|\n+", text)
            if segment.strip()
        ]
        return [segment for segment in segments if len(segment) >= 30]

    @classmethod
    def _extract_window(cls, text: str) -> tuple[str, tuple[str, ...]]:
        trace_steps = ["certfr_window_search_started"]
        segments = cls._split_candidate_segments(text)
        if not segments:
            trace_steps.append("certfr_no_segments_found")
            return text, tuple(trace_steps)

        matched_indices = [
            index
            for index, segment in enumerate(segments)
            if cls._count_markers(segment, cls.NOTIFICATION_MARKERS) > 0
        ]
        if not matched_indices:
            trace_steps.append("certfr_no_notification_window_found")
            return text, tuple(trace_steps)

        start = max(0, matched_indices[0] - 1)
        end = min(len(segments), matched_indices[0] + 3)
        candidate_window = " ".join(segments[start:end]).strip()
        trace_steps.append("certfr_notification_window_extracted")
        return candidate_window, tuple(trace_steps)

    @classmethod
    def _route_candidate(
        cls,
        text: str,
    ) -> tuple[str, str | None, str, tuple[str, ...]]:
        lowered_text = text.lower()
        trace_steps = ["certfr_cleaned"]
        if any(marker in lowered_text[:800] for marker in cls.REPORT_MARKERS):
            trace_steps.extend(
                [
                    "certfr_report_markers_detected",
                    "certfr_route_to_specialized_extractor",
                ]
            )
            return (
                "specialized_processing",
                "certfr_threat_intel_requires_extraction",
                "threat_intel",
                tuple(trace_steps),
            )

        if cls._count_markers(text, cls.EMBEDDED_MESSAGE_MARKERS) >= 2:
            trace_steps.extend(
                [
                    "certfr_embedded_message_detected",
                    "certfr_route_to_synthetic_lure_review",
                ]
            )
            return (
                "specialized_processing",
                "certfr_synthetic_lure_candidate",
                "synthetic_lure_candidate",
                tuple(trace_steps),
            )

        if cls._count_markers(text, cls.NOTIFICATION_MARKERS) > 0:
            trace_steps.append("certfr_context_only_window_detected")
            return (
                "specialized_processing",
                "certfr_notification_context_only",
                "procedural_notification",
                tuple(trace_steps),
            )

        trace_steps.append("certfr_irrecoverable_holdout_detected")
        return (
            "specialized_processing",
            "certfr_no_embedded_message",
            "irrecoverable_holdout",
            tuple(trace_steps),
        )

    @classmethod
    def _build_derived_payload(
        cls,
        *,
        extracted_text: str,
        raw_content: dict[str, Any],
        route_subtype: str | None,
        route_reason: str | None,
    ) -> dict[str, Any]:
        title = str(
            raw_content.get("title")
            or raw_content.get("subject")
            or raw_content.get("reference")
            or ""
        )
        iocs = CertFRCtiExtractor._extract_iocs(extracted_text)
        return {
            "derived_type": "certfr_stage_two_candidate",
            "candidate_subtype": route_subtype,
            "route_reason": route_reason,
            "is_synthetic": route_subtype == "synthetic_lure_candidate",
            "phishing_relevance": CertFRCtiExtractor._classify_phishing_relevance(
                extracted_text,
                title,
            ),
            "ioc_counts": {key: len(values) for key, values in iocs.items()},
            "iocs": iocs if route_subtype == "threat_intel" else {},
        }
