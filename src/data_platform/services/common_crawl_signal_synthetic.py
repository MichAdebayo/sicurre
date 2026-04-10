from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from data_platform.cleaning.normalization import text_sha256


class CommonCrawlSignalSyntheticService:
    FRENCH_MARKERS: tuple[str, ...] = (
        "bonjour",
        "veuillez",
        "confirmation",
        "votre",
        "aujourd'hui",
        "cordialement",
        "sécurité",
        "livraison",
        "colis",
    )
    TARGET_CUES: tuple[str, ...] = (
        "confirmer",
        "confirmation",
        "vérification",
        "verifier",
        "sécurité",
        "livraison",
        "suspendu",
        "maintenir",
    )

    @classmethod
    def build_drafts(
        cls,
        export_payload: dict[str, Any],
        *,
        variants_per_seed: int = 2,
    ) -> dict[str, Any]:
        seeds = [
            candidate
            for candidate in export_payload.get("candidates", [])
            if str(candidate.get("rule_key") or "") == "phishing_lure_candidate"
            and str(candidate.get("target_label") or "") == "phishing"
        ]

        drafts: list[dict[str, Any]] = []
        for seed in seeds:
            for variant_index in range(variants_per_seed):
                draft = cls._build_variant(seed, variant_index)
                drafts.append(draft)

        review_summary = Counter(
            str(draft.get("review_state") or "unknown") for draft in drafts
        )
        return {
            "mode": "common_crawl_signal_synthetic_drafts",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "seed_count": len(seeds),
            "draft_count": len(drafts),
            "review_summary": dict(review_summary),
            "drafts": drafts,
        }

    @classmethod
    def render_markdown(cls, payload: dict[str, Any]) -> str:
        lines = [
            "# Common Crawl Signal Synthetic Drafts",
            "",
            f"- Generated at: {payload.get('generated_at')}",
            f"- Seed count: {payload.get('seed_count')}",
            f"- Draft count: {payload.get('draft_count')}",
            f"- Review summary: {payload.get('review_summary')}",
            "",
        ]

        for draft in payload.get("drafts", []):
            lines.extend(
                [
                    f"## {draft['draft_id']}",
                    "",
                    f"- Scenario id: {draft['scenario_id']}",
                    f"- Target label: {draft['target_label']}",
                    f"- Review state: {draft['review_state']}",
                    f"- Review notes: {', '.join(draft.get('review_notes') or []) or 'none'}",
                    f"- Theme: {draft['primary_theme']}",
                    f"- Reference raw record: {draft['nearest_reference_raw_record_id']}",
                    "",
                    draft["normalized_text"],
                    "",
                ]
            )

        return "\n".join(lines)

    @classmethod
    def build_generation_samples(cls, payload: dict[str, Any]) -> list[dict[str, Any]]:
        samples: list[dict[str, Any]] = []
        for draft in payload.get("drafts", []):
            samples.append(
                {
                    "draft_id": draft["draft_id"],
                    "scenario_id": draft["scenario_id"],
                    "variant_index": draft["variant_index"],
                    "source_name": "common-crawl-phishing-signal",
                    "parent_source": draft["parent_source"],
                    "target_label": draft["target_label"],
                    "primary_theme": draft["primary_theme"],
                    "review_state": draft["review_state"],
                    "review_notes": list(draft.get("review_notes") or []),
                    "text_sha256": draft["text_sha256"],
                    "nearest_reference_raw_record_id": draft[
                        "nearest_reference_raw_record_id"
                    ],
                    "nearest_similarity": draft["nearest_similarity"],
                }
            )
        return samples

    @classmethod
    def _build_variant(cls, seed: dict[str, Any], variant_index: int) -> dict[str, Any]:
        normalized_text = str(seed.get("normalized_text") or "")
        subject, body = cls._split_subject_and_body(normalized_text)
        theme = cls._infer_theme(normalized_text)
        entity = cls._infer_entity(subject, body, theme)
        reference = cls._build_reference(seed, variant_index, theme)
        subject_variant, body_variant = cls._rewrite_variant(
            theme=theme,
            entity=entity,
            reference=reference,
            variant_index=variant_index,
        )
        full_text = f"Objet : {subject_variant}\n\n{body_variant}"
        review_state, review_notes = cls._assess_variant(full_text)
        raw_record_id = str(seed.get("raw_record_id") or "unknown")
        return {
            "draft_id": f"common-crawl-signal:{raw_record_id}:{variant_index}",
            "scenario_id": f"{theme}:{entity.lower().replace(' ', '_')}",
            "variant_index": variant_index,
            "parent_source": "common-crawl-bigdata",
            "target_label": "phishing",
            "primary_theme": theme,
            "review_state": review_state,
            "review_notes": review_notes,
            "normalized_text": full_text,
            "text_sha256": text_sha256(full_text),
            "nearest_reference_raw_record_id": raw_record_id,
            "nearest_similarity": 1.0,
            "seed_subject": subject,
        }

    @staticmethod
    def _split_subject_and_body(text: str) -> tuple[str, str]:
        parts = text.split("\n\n", 1)
        subject = parts[0].replace("Objet :", "", 1).strip() if parts else ""
        body = parts[1].strip() if len(parts) > 1 else ""
        return subject, body

    @staticmethod
    def _infer_theme(text: str) -> str:
        lowered = text.lower()
        if any(marker in lowered for marker in ("colis", "livraison", "relay")):
            return "delivery"
        if any(marker in lowered for marker in ("sécurité", "accès", "compte")):
            return "account_security"
        return "generic_security"

    @staticmethod
    def _infer_entity(subject: str, body: str, theme: str) -> str:
        if ":" in subject:
            return subject.split(":", 1)[0].strip()
        if theme == "delivery" and "Mondial Relay" in body:
            return "Mondial Relay"
        if theme == "account_security":
            return "Service sécurité"
        return "Service client"

    @staticmethod
    def _build_reference(seed: dict[str, Any], variant_index: int, theme: str) -> str:
        raw_record_id = str(seed.get("raw_record_id") or "seed")
        digest = (
            hashlib.sha256(f"{raw_record_id}:{variant_index}".encode("utf-8"))
            .hexdigest()
            .upper()
        )
        prefix = "CL" if theme == "delivery" else "ACC"
        return f"{prefix}-{digest[:6]}"

    @staticmethod
    def _rewrite_variant(
        *,
        theme: str,
        entity: str,
        reference: str,
        variant_index: int,
    ) -> tuple[str, str]:
        if theme == "delivery":
            subjects = (
                f"{entity} : confirmation requise pour votre livraison {reference}",
                f"{entity} : votre colis reste suspendu aujourd'hui",
            )
            bodies = (
                "Bonjour,\n\n"
                f"Votre colis référencé {reference} ne peut pas être remis tant qu'une vérification de vos coordonnées n'a pas été effectuée.\n\n"
                "Veuillez confirmer vos informations de réception aujourd'hui afin d'éviter le retour du pli au centre de distribution.\n\n"
                f"Cordialement,\n{entity}",
                "Bonjour,\n\n"
                f"Une nouvelle tentative de livraison liée au dossier {reference} reste suspendue après un échec de remise.\n\n"
                "Merci de vérifier immédiatement vos informations de livraison pour relancer l'acheminement sans délai.\n\n"
                f"Cordialement,\n{entity}",
            )
            return (
                subjects[variant_index % len(subjects)],
                bodies[variant_index % len(bodies)],
            )

        subjects = (
            f"{entity} : confirmation nécessaire pour maintenir votre accès {reference}",
            f"{entity} : vérification de sécurité en attente aujourd'hui",
        )
        bodies = (
            "Bonjour,\n\n"
            f"Une activité inhabituelle a été détectée sur le dossier {reference}.\n\n"
            "Veuillez confirmer vos éléments de sécurité aujourd'hui afin d'éviter la suspension préventive de votre accès.\n\n"
            f"Cordialement,\n{entity}",
            "Bonjour,\n\n"
            f"Nous avons besoin d'une confirmation liée au dossier {reference} pour finaliser la vérification de sécurité en cours.\n\n"
            "Merci de vérifier vos informations sans délai pour conserver l'accès à votre espace.\n\n"
            f"Cordialement,\n{entity}",
        )
        return (
            subjects[variant_index % len(subjects)],
            bodies[variant_index % len(bodies)],
        )

    @classmethod
    def _assess_variant(cls, text: str) -> tuple[str, list[str]]:
        lowered = text.lower()
        french_marker_count = sum(marker in lowered for marker in cls.FRENCH_MARKERS)
        target_cue_hits = sum(marker in lowered for marker in cls.TARGET_CUES)
        review_notes: list[str] = []
        if french_marker_count < 4:
            review_notes.append("weak_french_framing")
        if target_cue_hits < 2:
            review_notes.append("weak_target_alignment")
        if len(text) < 220:
            review_notes.append("body_too_short_for_review")
        if review_notes:
            return "needs_prompt_tuning", review_notes
        return "usable", []
