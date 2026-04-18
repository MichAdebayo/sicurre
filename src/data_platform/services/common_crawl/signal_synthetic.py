from __future__ import annotations

import hashlib
import re
import unicodedata
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

    DELIVERY_FALLBACK_ENTITIES: tuple[str, ...] = (
        "Mondial Relay",
        "Colissimo",
        "Chronopost",
        "La Poste",
        "Relais Colis",
    )
    ACCOUNT_FALLBACK_ENTITIES: tuple[str, ...] = (
        "FranceConnect",
        "Espace client sécurisé",
        "Portail d'authentification",
        "Centre de sécurité",
    )
    DELIVERY_SUBJECT_TEMPLATES: tuple[str, ...] = (
        "{entity} : confirmation requise pour votre livraison {reference}",
        "{entity} : votre colis reste suspendu aujourd'hui",
        "{entity} : dernière vérification avant remise du colis {reference}",
        "{entity} : nouvelle présentation bloquée sans confirmation",
        "{entity} : confirmez votre point relais pour le dossier {reference}",
        "{entity} : échec de remise, mise à jour attendue aujourd'hui",
    )
    DELIVERY_BODY_TEMPLATES: tuple[str, ...] = (
        "Bonjour,\n\nVotre colis référencé {reference} ne peut pas être remis tant qu'une vérification de vos coordonnées n'a pas été effectuée.\n\nVeuillez confirmer votre créneau de livraison depuis {link}.\n\nCordialement,\n{signature}",
        "Bonjour,\n\nUne nouvelle tentative de livraison liée au dossier {reference} reste suspendue après un échec de remise.\n\nPour relancer l'acheminement, ouvrez {link} et validez les informations demandées sans délai.\n\nCordialement,\n{signature}",
        "Bonjour,\n\nLe colis {reference} reste en attente au centre de distribution car la vérification de réception n'a pas été finalisée.\n\nMerci de confirmer votre disponibilité et votre adresse depuis {link} afin d'éviter le retour du pli.\n\nCordialement,\n{signature}",
        "Bonjour,\n\nNous n'avons pas pu confirmer la remise du dossier {reference} lors du dernier passage.\n\nUne mise à jour rapide de vos coordonnées est requise via {link} pour planifier une nouvelle présentation.\n\nCordialement,\n{signature}",
        "Bonjour,\n\nLe point relais associé au dossier {reference} reste bloqué faute de validation de votre part.\n\nVeuillez finaliser la vérification demandée depuis {link} pour conserver votre créneau de retrait.\n\nCordialement,\n{signature}",
        "Bonjour,\n\nVotre suivi {reference} signale une anomalie de distribution nécessitant une confirmation aujourd'hui.\n\nMerci de vérifier les informations de réception via {link} afin d'éviter une suspension définitive de l'acheminement.\n\nCordialement,\n{signature}",
    )
    ACCOUNT_SUBJECT_TEMPLATES: tuple[str, ...] = (
        "{entity} : confirmation nécessaire pour maintenir votre accès {reference}",
        "{entity} : vérification de sécurité en attente aujourd'hui",
        "{entity} : activité inhabituelle détectée sur votre espace",
        "{entity} : votre accès sera suspendu sans confirmation {reference}",
        "{entity} : action requise pour finaliser la vérification en cours",
        "{entity} : mise à jour de sécurité requise aujourd'hui",
    )
    ACCOUNT_BODY_TEMPLATES: tuple[str, ...] = (
        "Bonjour,\n\nUne activité inhabituelle a été détectée sur le dossier {reference}.\n\nVeuillez confirmer vos éléments de sécurité depuis {link} afin d'éviter la suspension préventive de votre accès.\n\nCordialement,\n{signature}",
        "Bonjour,\n\nNous avons besoin d'une confirmation liée au dossier {reference} pour finaliser la vérification de sécurité en cours.\n\nMerci d'ouvrir {link} pour vérifier les informations demandées et conserver l'accès à votre espace.\n\nCordialement,\n{signature}",
        "Bonjour,\n\nUne alerte de sécurité empêche la validation du dossier {reference} tant que votre identité numérique n'a pas été confirmée.\n\nUtilisez {link} pour vérifier les éléments demandés et maintenir votre accès sans interruption.\n\nCordialement,\n{signature}",
        "Bonjour,\n\nUne tentative de connexion non reconnue reste associée à la référence {reference}.\n\nAfin d'éviter une restriction temporaire, merci de confirmer vos informations depuis {link} dès réception de ce message.\n\nCordialement,\n{signature}",
        "Bonjour,\n\nLa vérification automatique du dossier {reference} n'a pas pu être finalisée.\n\nVeuillez reprendre la procédure via {link} pour conserver l'accès à vos services aujourd'hui.\n\nCordialement,\n{signature}",
        "Bonjour,\n\nNous avons suspendu à titre préventif une opération liée au dossier {reference} en attente d'une confirmation de sécurité.\n\nMerci d'ouvrir {link} afin de valider les informations demandées et lever l'alerte en cours.\n\nCordialement,\n{signature}",
    )
    DELIVERY_SIGNATURE_TEMPLATES: tuple[str, ...] = (
        "{entity}",
        "{entity} - Cellule de suivi",
        "{entity} - Service distribution",
    )
    ACCOUNT_SIGNATURE_TEMPLATES: tuple[str, ...] = (
        "{entity}",
        "{entity} - Support accès",
        "{entity} - Vérification identité",
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
            entity = subject.split(":", 1)[0].strip()
            if theme == "delivery" and entity.lower() in {
                "service livraison",
                "service client",
            }:
                return CommonCrawlSignalSyntheticService._fallback_entity(
                    seed_text=f"{subject}\n{body}",
                    theme=theme,
                )
            if theme == "account_security" and entity.lower() in {
                "service sécurité",
                "service securite",
                "service client",
            }:
                return CommonCrawlSignalSyntheticService._fallback_entity(
                    seed_text=f"{subject}\n{body}",
                    theme=theme,
                )
            return entity
        if theme == "delivery" and "Mondial Relay" in body:
            return "Mondial Relay"
        return CommonCrawlSignalSyntheticService._fallback_entity(
            seed_text=f"{subject}\n{body}",
            theme=theme,
        )

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
        variant_count = 6
        delivery_variant = CommonCrawlSignalSyntheticService._rotation_index(
            seed=f"delivery:{entity}:{reference}",
            variant_index=variant_index,
            modulo=variant_count,
        )
        account_variant = CommonCrawlSignalSyntheticService._rotation_index(
            seed=f"account:{entity}:{reference}",
            variant_index=variant_index,
            modulo=variant_count,
        )
        if theme == "delivery":
            link = CommonCrawlSignalSyntheticService._build_safe_link(
                entity=entity,
                theme=theme,
                reference=reference,
                action=delivery_variant,
            )
            signature = CommonCrawlSignalSyntheticService.DELIVERY_SIGNATURE_TEMPLATES[
                delivery_variant
                % len(CommonCrawlSignalSyntheticService.DELIVERY_SIGNATURE_TEMPLATES)
            ].format(entity=entity)
            subjects = tuple(
                template.format(entity=entity, reference=reference)
                for template in CommonCrawlSignalSyntheticService.DELIVERY_SUBJECT_TEMPLATES
            )
            bodies = tuple(
                template.format(reference=reference, link=link, signature=signature)
                for template in CommonCrawlSignalSyntheticService.DELIVERY_BODY_TEMPLATES
            )
            return (
                subjects[delivery_variant],
                bodies[delivery_variant],
            )

        link = CommonCrawlSignalSyntheticService._build_safe_link(
            entity=entity,
            theme=theme,
            reference=reference,
            action=account_variant,
        )
        signature = CommonCrawlSignalSyntheticService.ACCOUNT_SIGNATURE_TEMPLATES[
            account_variant
            % len(CommonCrawlSignalSyntheticService.ACCOUNT_SIGNATURE_TEMPLATES)
        ].format(entity=entity)
        subjects = tuple(
            template.format(entity=entity, reference=reference)
            for template in CommonCrawlSignalSyntheticService.ACCOUNT_SUBJECT_TEMPLATES
        )
        bodies = tuple(
            template.format(reference=reference, link=link, signature=signature)
            for template in CommonCrawlSignalSyntheticService.ACCOUNT_BODY_TEMPLATES
        )
        return (
            subjects[account_variant],
            bodies[account_variant],
        )

    @staticmethod
    def _rotation_index(seed: str, variant_index: int, modulo: int) -> int:
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        base = int(digest[:8], 16) % modulo
        return (base + variant_index) % modulo

    @staticmethod
    def _slugify_entity(entity: str) -> str:
        normalized = unicodedata.normalize("NFKD", entity)
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
        return slug or "espace-client"

    @classmethod
    def _build_safe_link(
        cls,
        *,
        entity: str,
        theme: str,
        reference: str,
        action: int,
    ) -> str:
        entity_slug = cls._slugify_entity(entity)
        action_slug = "livraison" if theme == "delivery" else "verification"
        endpoint = (
            "confirmer",
            "maintien",
            "controle",
            "mise-a-jour",
            "validation",
            "acces",
        )[action % 6]
        return f"https://{entity_slug}.{action_slug}.example/{endpoint}/{reference.lower()}"

    @classmethod
    def _fallback_entity(cls, *, seed_text: str, theme: str) -> str:
        pools = {
            "delivery": cls.DELIVERY_FALLBACK_ENTITIES,
            "account_security": cls.ACCOUNT_FALLBACK_ENTITIES,
            "generic_security": cls.ACCOUNT_FALLBACK_ENTITIES,
        }
        pool = pools.get(theme, cls.ACCOUNT_FALLBACK_ENTITIES)
        digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
        return pool[int(digest[:8], 16) % len(pool)]

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
