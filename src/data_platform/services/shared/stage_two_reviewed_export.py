from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data_platform.cleaning.normalization import TextNormalizationService


class StageTwoReviewedExportService:
    LABEL_TO_ID: dict[str, int] = {
        "phishing": 0,
        "spam": 1,
        "legitimate": 2,
    }
    CSV_COLUMNS: list[str] = [
        "text",
        "label",
        "source",
        "language",
        "archetype",
        "text_len",
        "candidate_id",
        "draft_id",
        "raw_record_id",
        "target_label",
        "review_state",
        "text_sha256",
    ]
    LEGITIMATE_EXPORT_BLOCKERS: tuple[str, ...] = (
        "page_like_legitimate_subject",
        "fragment_like_legitimate_subject",
    )
    LEGITIMATE_SUBJECT_MARKERS: tuple[str, ...] = (
        "selon les conditions générales",
        "en outre",
        "en second lieu",
        "tous les champs sont obligatoires",
        "notice d'information",
        "historique des remises",
        "les 3 modes de gestion",
        "services digitaux",
        "gestion compte bancaire",
        "identifier facilement les aides",
        "des intérêts débiteurs",
        "télécharger la notice",
        "l’organisateur se réserve",
        "l'organisateur se réserve",
        "etape ",
        "étape ",
        "# paiement",
        "conformément à cette dernière exigence réglementaire",
        "actuellement nous travaillons",
        "rapprochez-vous de votre conseiller habituel",
        "[phone]service",
    )

    def __init__(
        self,
        normalization_service: TextNormalizationService | None = None,
    ) -> None:
        self.normalization_service = normalization_service or TextNormalizationService()

    def build_export(
        self,
        draft_payload: dict[str, Any],
        *,
        eligible_review_states: tuple[str, ...] = ("usable",),
    ) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        seen_hashes: set[str] = set()
        skipped_state_summary: Counter[str] = Counter()
        skipped_reason_summary: Counter[str] = Counter()
        label_summary: Counter[str] = Counter()

        for draft in draft_payload.get("drafts", []):
            review_state = str(draft.get("review_state") or "unknown")
            if review_state not in eligible_review_states:
                skipped_state_summary.update([review_state])
                continue

            candidate = self._build_candidate(draft)
            if candidate is None:
                skipped_reason_summary.update(["unknown_target_label"])
                continue

            text_sha256 = str(candidate.get("text_sha256") or "")
            if text_sha256 in seen_hashes:
                skipped_reason_summary.update(["duplicate_text_sha256"])
                continue
            seen_hashes.add(text_sha256)

            if candidate.get("normalization_rejection"):
                skipped_reason_summary.update(
                    [str(candidate.get("normalization_rejection"))]
                )
                continue

            if target_label := str(candidate.get("target_label") or ""):
                if target_label == "legitimate":
                    blocker_reason = self._legitimate_quality_blocker(
                        draft=draft,
                        candidate=candidate,
                    )
                    if blocker_reason is not None:
                        skipped_reason_summary.update([blocker_reason])
                        continue

            candidates.append(candidate)
            label_summary.update([str(candidate.get("target_label") or "unknown")])

        return {
            "mode": "stage_two_reviewed_export",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "eligible_review_states": list(eligible_review_states),
            "exported_candidate_count": len(candidates),
            "skipped_state_summary": dict(skipped_state_summary),
            "skipped_reason_summary": dict(skipped_reason_summary),
            "label_summary": dict(label_summary),
            "candidates": candidates,
        }

    @classmethod
    def render_markdown(cls, export_payload: dict[str, Any]) -> str:
        lines = [
            "# Stage-Two Reviewed Export",
            "",
            f"- Generated at: {export_payload.get('generated_at')}",
            f"- Eligible review states: {export_payload.get('eligible_review_states')}",
            f"- Exported candidate count: {export_payload.get('exported_candidate_count')}",
            f"- Label summary: {export_payload.get('label_summary')}",
            f"- Skipped state summary: {export_payload.get('skipped_state_summary')}",
            f"- Skipped reason summary: {export_payload.get('skipped_reason_summary')}",
            "",
        ]

        for candidate in export_payload.get("candidates", []):
            lines.extend(
                [
                    f"## {candidate['candidate_id']}",
                    "",
                    f"- Source: {candidate['source_name']}",
                    f"- Raw record id: {candidate['raw_record_id']}",
                    f"- Target label: {candidate['target_label']} ({candidate['label_id']})",
                    f"- Review state: {candidate['review_state']}",
                    f"- Archetype: {candidate['corpus_row']['archetype']}",
                    f"- Text length: {candidate['text_length']}",
                    "",
                    candidate.get("normalized_text") or "",
                    "",
                ]
            )

        return "\n".join(lines)

    @classmethod
    def write_csv(cls, export_payload: dict[str, Any], output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            cls._candidate_to_csv_row(candidate)
            for candidate in export_payload.get("candidates", [])
        ]
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=cls.CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    def _build_candidate(self, draft: dict[str, Any]) -> dict[str, Any] | None:
        target_label = str(draft.get("target_label") or "")
        if target_label not in self.LABEL_TO_ID:
            return None

        full_text = str(draft.get("full_text") or "")
        artifact = self.normalization_service.normalize_text(full_text)
        source_name = str(draft.get("source_name") or "unknown")
        rule_key = str(draft.get("rule_key") or "unknown")
        candidate_id = f"reviewed-export:{draft.get('draft_id') or 'unknown'}"
        corpus_source = f"stage2_reviewed_{source_name.replace('-', '_')}"
        archetype = f"{rule_key}:{draft.get('rewrite_mode') or 'rewrite'}"

        return {
            "candidate_id": candidate_id,
            "draft_id": draft.get("draft_id"),
            "job_id": draft.get("job_id"),
            "raw_record_id": draft.get("raw_record_id"),
            "source_name": source_name,
            "rule_key": rule_key,
            "rewrite_mode": draft.get("rewrite_mode"),
            "target_label": target_label,
            "label_id": self.LABEL_TO_ID[target_label],
            "review_state": draft.get("review_state"),
            "review_notes": draft.get("review_notes", []),
            "quality_signals": draft.get("quality_signals", {}),
            "normalized_text": artifact.cleaned_text,
            "text_length": artifact.text_length,
            "text_sha256": artifact.text_sha256,
            "contains_pii": artifact.contains_redaction_tokens,
            "redaction_status": (
                "redacted" if artifact.contains_redaction_tokens else "not_required"
            ),
            "normalization_rejection": artifact.rejection_reason,
            "corpus_row": {
                "text": artifact.cleaned_text,
                "label": self.LABEL_TO_ID[target_label],
                "source": corpus_source,
                "language": "fr",
                "archetype": archetype,
                "text_len": artifact.text_length,
            },
        }

    @classmethod
    def _candidate_to_csv_row(cls, candidate: dict[str, Any]) -> dict[str, Any]:
        corpus_row = candidate.get("corpus_row", {})
        return {
            "text": corpus_row.get("text", ""),
            "label": corpus_row.get("label", ""),
            "source": corpus_row.get("source", ""),
            "language": corpus_row.get("language", ""),
            "archetype": corpus_row.get("archetype", ""),
            "text_len": corpus_row.get("text_len", ""),
            "candidate_id": candidate.get("candidate_id", ""),
            "draft_id": candidate.get("draft_id", ""),
            "raw_record_id": candidate.get("raw_record_id", ""),
            "target_label": candidate.get("target_label", ""),
            "review_state": candidate.get("review_state", ""),
            "text_sha256": candidate.get("text_sha256", ""),
        }

    @classmethod
    def _legitimate_quality_blocker(
        cls,
        *,
        draft: dict[str, Any],
        candidate: dict[str, Any],
    ) -> str | None:
        review_notes = {str(note) for note in draft.get("review_notes", [])}
        if review_notes.intersection(cls.LEGITIMATE_EXPORT_BLOCKERS):
            for blocker in cls.LEGITIMATE_EXPORT_BLOCKERS:
                if blocker in review_notes:
                    return blocker
        subject_line = str(candidate.get("normalized_text") or "").split("\n", 1)[0]
        lowered_subject = subject_line.lower()
        if any(marker in lowered_subject for marker in cls.LEGITIMATE_SUBJECT_MARKERS):
            return "page_like_legitimate_subject"
        return None
