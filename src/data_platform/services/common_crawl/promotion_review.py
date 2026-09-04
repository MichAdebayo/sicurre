from __future__ import annotations

import re
from collections import Counter, defaultdict
from statistics import mean
from typing import Any

from db.models import AnnotationLabelSource


class CommonCrawlPromotionReviewService:
    DEFAULT_APPROVED_SUBTYPES = (
        "transactional_legitimate",
        "instructional_legitimate",
        "promotional_spam",
    )
    DIRECT_WRITE_COMPARABLE_RULE_KEYS = (
        "instructional_legitimate",
        "promotional_spam",
    )
    MIN_FRENCH_MARKERS_BY_LABEL: dict[str, int] = {
        "legitimate": 4,
        "spam": 3,
    }
    MIN_TARGET_CUES_BY_LABEL: dict[str, int] = {
        "legitimate": 1,
        "spam": 1,
    }
    TEXT_RESIDUE_MARKERS: tuple[str, ...] = (
        " de les ",
        " à les ",
        " question de les ",
        " liée à les ",
        " lié à les ",
    )
    BODY_RESIDUE_MARKERS: tuple[str, ...] = (
        "et à vos échanges en ligne",
        "lorsqu'il est question des messages suspects",
        "lorsqu'il est question des appels frauduleux",
    )
    PROMOTIONAL_PAGE_RESIDUE_MARKERS: tuple[str, ...] = (
        "ce site",
        "tous les articles",
        "questions diverses",
        "cdiscount",
        "brico",
        "*$",
        "« ",
    )
    MALFORMED_SUBJECT_MARKERS: tuple[str, ...] = (
        "(pdf",
        "(doc",
        "(xls",
    )
    MALFORMED_SUBJECT_PATTERNS: tuple[str, ...] = (
        r"\b(?:cliquez|ouvrez|changez|confirmez|validez|activez|renseignez|consultez)\b",
        r"\b(?:à|de|du|des|sur|avec|pour)\s*$",
    )
    WEAK_SUBJECT_PATTERNS: tuple[str, ...] = (
        r"^objet\s*:\s*(?:vous\s|comment\b|qu[’']est-ce que\b|révélez\b|revelez\b)",
        r"^objet\s*:\s*(?:loisirs vacances voyage|investissement financement territoire|dans le cas|accéder\b|acceder\b)",
        r"\blecture\s*:",
    )
    SUBJECT_GRAMMAR_RESIDUE_PATTERNS: tuple[str, ...] = (
        r"\bde des\b",
        r"\bsur accéder\b",
        r"\bsur acceder\b",
        r"\bpour dans le cas\b",
    )
    REVIEW_NOTE_BLOCKERS: tuple[str, ...] = (
        "duplicate_generated_draft",
        "page_like_legitimate_subject",
        "fragment_like_legitimate_subject",
    )

    @classmethod
    def build_plan(
        cls,
        review_payload: dict[str, Any],
        *,
        approved_subtypes: tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        approved = approved_subtypes or cls.DEFAULT_APPROVED_SUBTYPES
        samples = cls._collect_samples(review_payload)
        autopromotable: list[dict[str, Any]] = []
        manual_review: list[dict[str, Any]] = []
        quality_by_subtype: dict[str, dict[str, Any]] = {}

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for sample in samples:
            subtype = sample.get("route_subtype")
            if subtype:
                grouped[str(subtype)].append(sample)

            if subtype not in approved:
                continue
            if sample.get("route_outcome") == "accepted":
                autopromotable.append(sample)
            elif sample.get("route_outcome") == "specialized_processing":
                manual_review.append(sample)

        for subtype, subtype_samples in grouped.items():
            quality_by_subtype[subtype] = cls._build_quality_metrics(subtype_samples)

        return {
            "mode": "no_write_promotion_review",
            "source_name": review_payload.get("source_name"),
            "approved_subtypes": list(approved),
            "reviewed_sample_count": len(samples),
            "autopromotable_count": len(autopromotable),
            "manual_review_count": len(manual_review),
            "autopromotable_record_ids": [
                sample["raw_record_id"] for sample in autopromotable
            ],
            "manual_review_record_ids": [
                sample["raw_record_id"] for sample in manual_review
            ],
            "quality_by_subtype": quality_by_subtype,
            "route_summary": cls._merge_source_summaries(
                review_payload, "route_summary"
            ),
            "subtype_summary": cls._merge_source_summaries(
                review_payload, "subtype_summary"
            ),
            "rejection_summary": cls._merge_source_summaries(
                review_payload, "rejection_summary"
            ),
        }

    @classmethod
    def build_acceptance_review(
        cls,
        export_payload: dict[str, Any],
    ) -> dict[str, Any]:
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        rejection_summary: Counter[str] = Counter()
        accepted_label_summary: Counter[str] = Counter()

        for candidate in export_payload.get("candidates", []):
            decision_reason = cls._evaluate_candidate(candidate)
            shaped_candidate = {
                "candidate_id": candidate.get("candidate_id"),
                "draft_id": candidate.get("draft_id"),
                "raw_record_id": candidate.get("raw_record_id"),
                "source_name": candidate.get("source_name"),
                "rule_key": candidate.get("rule_key"),
                "rewrite_mode": candidate.get("rewrite_mode"),
                "target_label": candidate.get("target_label"),
                "review_state": candidate.get("review_state"),
                "review_notes": list(candidate.get("review_notes") or []),
                "quality_signals": dict(candidate.get("quality_signals") or {}),
                "text_length": candidate.get("text_length"),
                "text_sha256": candidate.get("text_sha256"),
                "normalized_text": candidate.get("normalized_text"),
                "acceptance_reason": decision_reason,
            }
            if decision_reason == "accepted_for_curated_pilot":
                accepted.append(shaped_candidate)
                accepted_label_summary.update([str(candidate.get("target_label"))])
            else:
                rejected.append(shaped_candidate)
                rejection_summary.update([decision_reason])

        proposed_normalized_messages = [
            {
                "raw_record_id": candidate["raw_record_id"],
                "normalized_text": candidate["normalized_text"],
                "text_sha256": candidate["text_sha256"],
                "language": "fr",
                "current_label": candidate["target_label"],
                "contains_pii": False,
                "redaction_status": "not_required",
                "text_length": candidate["text_length"],
                "lineage_source": candidate["source_name"],
                "lineage_stage": "common_crawl_reviewed_export",
                "lineage_candidate_id": candidate["candidate_id"],
            }
            for candidate in accepted
        ]
        proposed_annotations = [
            {
                "candidate_id": candidate["candidate_id"],
                "raw_record_id": candidate["raw_record_id"],
                "label": candidate["target_label"],
                "label_source": AnnotationLabelSource.COMMON_CRAWL_ACCEPTANCE_REVIEW.value,
                "confidence": 0.8,
                "comment": "No-write proposed annotation pending curated promotion.",
                "is_validated": False,
            }
            for candidate in accepted
        ]

        return {
            "mode": "common_crawl_acceptance_review",
            "source_name": "common-crawl-bigdata",
            "comparison_mode": "conservative_parity_with_direct_write_sources",
            "reviewed_candidate_count": len(export_payload.get("candidates", [])),
            "accepted_candidate_count": len(accepted),
            "rejected_candidate_count": len(rejected),
            "accepted_label_summary": dict(accepted_label_summary),
            "rejection_summary": dict(rejection_summary),
            "accepted_candidates": accepted,
            "rejected_candidates": rejected,
            "proposed_normalized_messages": proposed_normalized_messages,
            "proposed_annotations": proposed_annotations,
        }

    @classmethod
    def render_acceptance_markdown(cls, payload: dict[str, Any]) -> str:
        lines = [
            "# Common Crawl Acceptance Review",
            "",
            f"- Source: {payload.get('source_name')}",
            f"- Comparison mode: {payload.get('comparison_mode')}",
            f"- Reviewed candidates: {payload.get('reviewed_candidate_count')}",
            f"- Accepted candidates: {payload.get('accepted_candidate_count')}",
            f"- Rejected candidates: {payload.get('rejected_candidate_count')}",
            f"- Accepted label summary: {payload.get('accepted_label_summary')}",
            f"- Rejection summary: {payload.get('rejection_summary')}",
            "",
            "## Accepted Candidates",
            "",
        ]

        for candidate in payload.get("accepted_candidates", []):
            lines.extend(
                [
                    f"### {candidate['candidate_id']}",
                    f"- Rule key: {candidate['rule_key']}",
                    f"- Target label: {candidate['target_label']}",
                    f"- Text length: {candidate['text_length']}",
                    f"- Acceptance reason: {candidate['acceptance_reason']}",
                    "",
                ]
            )

        lines.extend(["## Rejected Candidates", ""])
        for candidate in payload.get("rejected_candidates", []):
            lines.extend(
                [
                    f"### {candidate['candidate_id']}",
                    f"- Rule key: {candidate['rule_key']}",
                    f"- Target label: {candidate['target_label']}",
                    f"- Rejection reason: {candidate['acceptance_reason']}",
                    "",
                ]
            )

        return "\n".join(lines)

    @classmethod
    def _evaluate_candidate(cls, candidate: dict[str, Any]) -> str:
        rule_key = str(candidate.get("rule_key") or "")
        if rule_key not in cls.DIRECT_WRITE_COMPARABLE_RULE_KEYS:
            return "subtype_not_comparable_to_direct_write"

        if str(candidate.get("review_state") or "") != "usable":
            return "review_state_not_usable"

        review_notes = {str(note) for note in candidate.get("review_notes") or []}
        if review_notes.intersection(cls.REVIEW_NOTE_BLOCKERS):
            return "blocked_review_note_present"
        if review_notes:
            return "review_notes_present"

        if bool(candidate.get("contains_pii")):
            return "pii_not_allowed"
        if str(candidate.get("redaction_status") or "") != "not_required":
            return "redaction_review_required"

        target_label = str(candidate.get("target_label") or "")
        quality_signals = dict(candidate.get("quality_signals") or {})
        french_marker_count = int(quality_signals.get("french_marker_count") or 0)
        target_cue_hits = int(quality_signals.get("target_cue_hits") or 0)
        if french_marker_count < cls.MIN_FRENCH_MARKERS_BY_LABEL.get(target_label, 3):
            return "weak_french_marker_density"
        if target_cue_hits < cls.MIN_TARGET_CUES_BY_LABEL.get(target_label, 1):
            return "weak_target_cue_alignment"

        normalized_text = str(candidate.get("normalized_text") or "")
        lowered_text = f" {normalized_text.lower()} "
        subject_line = normalized_text.split("\n", 1)[0].lower().strip()
        if any(marker in lowered_text for marker in cls.TEXT_RESIDUE_MARKERS):
            return "grammar_residue_detected"
        if any(
            re.search(pattern, subject_line)
            for pattern in cls.SUBJECT_GRAMMAR_RESIDUE_PATTERNS
        ):
            return "grammar_residue_detected"
        if any(marker in lowered_text for marker in cls.BODY_RESIDUE_MARKERS):
            return "body_residue_detected"
        if any(
            re.search(pattern, subject_line) for pattern in cls.WEAK_SUBJECT_PATTERNS
        ):
            return "weak_subject_detected"
        if cls._has_malformed_subject_fragment(normalized_text):
            return "malformed_subject_fragment_detected"
        if rule_key == "promotional_spam" and cls._has_promotional_page_residue(
            normalized_text
        ):
            return "promotional_page_residue_detected"

        text_length = int(candidate.get("text_length") or 0)
        if text_length < 180 or text_length > 520:
            return "text_length_outside_curated_envelope"

        return "accepted_for_curated_pilot"

    @classmethod
    def _has_promotional_page_residue(cls, normalized_text: str) -> bool:
        lowered = normalized_text.lower()
        if any(marker in lowered for marker in cls.PROMOTIONAL_PAGE_RESIDUE_MARKERS):
            return True
        if re.search(r"\b\d{2}/\d{2}/\d{4}\b", lowered):
            return True
        if re.search(r"\b\d+\s*min\b", lowered):
            return True
        return False

    @classmethod
    def _has_malformed_subject_fragment(cls, normalized_text: str) -> bool:
        subject_line = normalized_text.split("\n", 1)[0].lower()
        if any(marker in subject_line for marker in cls.MALFORMED_SUBJECT_MARKERS):
            return True
        if subject_line.count("#") >= 1:
            return True
        if subject_line.count("(") != subject_line.count(")"):
            return True
        if any(
            re.search(pattern, subject_line)
            for pattern in cls.MALFORMED_SUBJECT_PATTERNS
        ):
            return True
        return False

    @staticmethod
    def _collect_samples(review_payload: dict[str, Any]) -> list[dict[str, Any]]:
        samples: list[dict[str, Any]] = []
        result = review_payload.get("result", {})
        for source_groups in result.get("parent_sources", {}).values():
            for group in source_groups:
                samples.extend(group.get("samples", []))
        return samples

    @staticmethod
    def _merge_source_summaries(
        review_payload: dict[str, Any],
        key: str,
    ) -> dict[str, int]:
        summary: Counter[str] = Counter()
        result = review_payload.get("result", {})
        for source_groups in result.get("parent_sources", {}).values():
            for group in source_groups:
                summary.update(group.get(key, {}))
        return dict(summary)

    @staticmethod
    def _build_quality_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
        similarities = [
            sample["similarity_score"]
            for sample in samples
            if isinstance(sample.get("similarity_score"), (int, float))
        ]
        normalized_lengths = [
            sample["normalized_length"]
            for sample in samples
            if isinstance(sample.get("normalized_length"), int)
        ]
        transformation_summary = Counter(
            str(sample.get("transformation_strength"))
            for sample in samples
            if sample.get("transformation_strength")
        )
        promotion_eligible_count = len(
            [
                sample
                for sample in samples
                if bool((sample.get("derived_payload") or {}).get("promotion_eligible"))
            ]
        )
        return {
            "sample_count": len(samples),
            "avg_similarity": round(mean(similarities), 3) if similarities else None,
            "avg_normalized_length": (
                round(mean(normalized_lengths), 1) if normalized_lengths else None
            ),
            "major_transformation_count": transformation_summary.get("major", 0),
            "promotion_eligible_count": promotion_eligible_count,
            "transformation_summary": dict(transformation_summary),
        }
