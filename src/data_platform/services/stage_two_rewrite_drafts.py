from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from data_platform.cleaning.normalization import clean_text, text_sha256


class StageTwoRewriteDraftService:
    FRENCH_MARKERS: tuple[str, ...] = (
        "bonjour",
        "cordialement",
        "veuillez",
        "votre",
        "vous",
        "aujourd'hui",
        "service client",
        "offre",
        "accès",
        "compte",
        "sécurité",
        "cliquez",
        "confirmez",
        "profitez",
    )
    MOJIBAKE_MARKERS: tuple[str, ...] = ("Ã", "Â", "вЂ", "рџ", "�")
    TARGET_CUES: dict[str, tuple[str, ...]] = {
        "legitimate": (
            "service client",
            "nous vous rappelons",
            "en cas de doute",
            "espace habituel",
            "sécurité",
        ),
        "spam": (
            "offre",
            "bonus",
            "gratuit",
            "profitez",
            "avantage",
            "jusqu'à ce soir",
        ),
        "phishing": (
            "action requise",
            "confirmez",
            "sans délai",
            "suspension",
            "vérification",
        ),
    }

    @classmethod
    def build_drafts(cls, job_payload: dict[str, Any]) -> dict[str, Any]:
        drafts: list[dict[str, Any]] = []

        for job in job_payload.get("jobs", []):
            draft = cls._build_draft(job)
            drafts.append(draft)

        cls._apply_duplicate_review_flags(drafts)

        review_summary = Counter(draft["review_state"] for draft in drafts)
        target_label_summary = Counter(str(draft["target_label"]) for draft in drafts)

        return {
            "mode": "stage_two_rewrite_drafts",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "draft_count": len(drafts),
            "review_summary": dict(review_summary),
            "target_label_summary": dict(target_label_summary),
            "drafts": drafts,
        }

    @staticmethod
    def render_markdown(draft_payload: dict[str, Any]) -> str:
        lines = [
            "# Stage-Two Rewrite Drafts",
            "",
            f"- Generated at: {draft_payload.get('generated_at')}",
            f"- Draft count: {draft_payload.get('draft_count')}",
            f"- Review summary: {draft_payload.get('review_summary')}",
            f"- Target label summary: {draft_payload.get('target_label_summary')}",
            "",
        ]

        for draft in draft_payload.get("drafts", []):
            lines.extend(
                [
                    f"## {draft['draft_id']}",
                    "",
                    f"- Job id: {draft['job_id']}",
                    f"- Source: {draft['source_name']}",
                    f"- Rewrite mode: {draft['rewrite_mode']}",
                    f"- Target label: {draft['target_label']}",
                    f"- Review state: {draft['review_state']}",
                    f"- Review notes: {', '.join(draft.get('review_notes', [])) or 'none'}",
                    f"- Quality signals: {draft.get('quality_signals')}",
                    "",
                    f"### Subject\n\n{draft['subject']}\n",
                    f"### Body\n\n{draft['body']}\n",
                ]
            )

        return "\n".join(lines)

    @classmethod
    def _build_draft(cls, job: dict[str, Any]) -> dict[str, Any]:
        source_preview = clean_text(str(job.get("source_preview") or ""))
        subject, body = cls._rewrite_job(job, source_preview)
        full_text = clean_text(f"Objet : {subject}\n\n{body}")
        review_state, review_notes, quality_signals = cls._assess_draft(
            job=job,
            source_preview=source_preview,
            subject=subject,
            body=body,
            full_text=full_text,
        )

        return {
            "draft_id": str(job.get("job_id") or "unknown"),
            "job_id": job.get("job_id"),
            "source_name": job.get("source_name"),
            "rule_key": job.get("rule_key"),
            "rewrite_mode": job.get("rewrite_mode"),
            "target_label": job.get("target_label"),
            "raw_record_id": job.get("raw_record_id"),
            "review_state": review_state,
            "review_notes": review_notes,
            "quality_signals": quality_signals,
            "subject": subject,
            "body": body,
            "full_text": full_text,
            "text_sha256": text_sha256(full_text),
            "constraints": job.get("constraints", []),
            "prompt_hints": job.get("prompt_hints", []),
            "source_preview": source_preview,
        }

    @classmethod
    def _rewrite_job(
        cls,
        job: dict[str, Any],
        source_preview: str,
    ) -> tuple[str, str]:
        if not source_preview:
            return (
                "Brouillon à revoir",
                "Bonjour,\n\nLe contenu source est insuffisant pour produire une reformulation fiable.\n\nCordialement,\nRevue stage-two",
            )

        rewrite_mode = str(job.get("rewrite_mode") or "rewrite")
        match rewrite_mode:
            case "institutional_page_to_notification":
                return cls._build_legitimate_notification(source_preview)
            case "promotional_page_to_spam_message":
                return cls._build_promotional_spam(source_preview)
            case "repair_then_rewrite":
                return cls._build_repaired_spam(source_preview)
            case "embedded_lure_to_phishing_email":
                return cls._build_phishing_draft(source_preview)
            case _:
                return cls._build_generic_rewrite(source_preview, job)

    @classmethod
    def _build_legitimate_notification(cls, source_preview: str) -> tuple[str, str]:
        lowered = source_preview.lower()
        focus = cls._infer_legitimate_focus(source_preview)
        variant = cls._variant_index(source_preview, 4)
        if any(marker in lowered for marker in ("réseaux sociaux", "internet")):
            subjects = (
                f"Vigilance renforcée concernant {focus}",
                f"Rappel de sécurité au sujet de {focus}",
                f"Conseils utiles pour {focus}",
                f"Point d'attention concernant {focus}",
            )
            return (
                subjects[variant],
                f"Bonjour,\n\nNous vous invitons à rester particulièrement vigilant face aux messages diffusés par e-mail, SMS ou sur les réseaux sociaux lorsqu'ils demandent une action urgente en lien avec {focus.lower()}.\n\nNe communiquez jamais vos données personnelles ou bancaires à la suite d'un message inattendu et privilégiez toujours votre espace habituel ou un contact direct avec votre service client.\n\nCordialement,\nVotre service client",
            )

        if any(
            marker in lowered
            for marker in ("fraude", "escroquer", "douteux", "données bancaires")
        ):
            subjects = (
                f"Rappel de vigilance concernant {focus}",
                f"Alerte de prudence au sujet de {focus}",
                f"Bonnes pratiques liées à {focus}",
                f"Sécurité renforcée pour {focus}",
            )
            return (
                subjects[variant],
                f"Bonjour,\n\nNous vous rappelons de ne jamais transmettre vos données bancaires, vos codes de validation ou vos informations personnelles par e-mail, SMS ou téléphone, notamment lorsqu'un message inattendu évoque {focus.lower()}.\n\nEn cas de message douteux, connectez-vous uniquement à votre espace habituel ou rapprochez-vous de votre service client avant toute action.\n\nCordialement,\nVotre service client",
            )

        if any(
            marker in lowered
            for marker in ("mot de passe", "connexion", "accès", "compte")
        ):
            subjects = (
                f"Information sur la sécurisation de {focus.lower()}",
                f"Mise à jour utile concernant {focus.lower()}",
                f"Conseils de sécurité pour {focus.lower()}",
                f"Point de contrôle lié à {focus.lower()}",
            )
            return (
                subjects[variant],
                f"Bonjour,\n\nSi vous devez réinitialiser {focus.lower()}, suivez uniquement les étapes disponibles depuis votre espace habituel.\n\nSelon votre situation, un code temporaire pourra vous être transmis par SMS ou par courrier. En cas de doute, contactez votre conseiller avant toute saisie d'information.\n\nCordialement,\nVotre service client",
            )

        subjects = (
            f"Information utile concernant {focus.lower()}",
            f"Rappel pratique au sujet de {focus.lower()}",
            f"Point d'information pour {focus.lower()}",
            f"Mise au point utile concernant {focus.lower()}",
        )
        return (
            subjects[variant],
            f"Bonjour,\n\nNous vous adressons ce rappel afin de vous aider à vérifier les bonnes pratiques liées à {focus.lower()} et à vos échanges en ligne.\n\nPour toute demande sensible, utilisez uniquement les canaux habituels et rapprochez-vous de votre service client si vous avez le moindre doute.\n\nCordialement,\nVotre service client",
        )

    @classmethod
    def _build_promotional_spam(cls, source_preview: str) -> tuple[str, str]:
        topic = cls._infer_promotional_topic(source_preview)
        variant = cls._variant_index(source_preview, 4)
        subject_templates = (
            f"{topic} : votre offre réservée jusqu'à ce soir",
            f"{topic} : dernières heures pour en profiter",
            f"{topic} : réponse prioritaire aujourd'hui",
            f"{topic} : avantage immédiat sur demande",
        )
        intro_templates = (
            f"Profitez dès maintenant de {topic.lower()} avec un avantage exclusif réservé aux demandes traitées aujourd'hui.",
            f"Une proposition liée à {topic.lower()} est disponible dès maintenant avec une remise limitée dans le temps.",
            f"Votre accès à {topic.lower()} peut être activé aujourd'hui avec des conditions préférentielles et une réponse rapide.",
            f"Nous mettons à votre disposition {topic.lower()} avec une offre prioritaire valable sur les demandes reçues aujourd'hui.",
        )
        cta_templates = (
            "Répondez à ce message pour recevoir le détail de l'offre et activer votre avantage avant la fin de la journée.",
            "Confirmez simplement votre intérêt par retour d'e-mail pour recevoir la proposition complète sans attendre.",
            "Demandez le récapitulatif de l'offre maintenant pour bloquer votre avantage avant la clôture du jour.",
            "Répondez dès aujourd'hui pour recevoir les conditions détaillées et profiter de la priorité de traitement.",
        )
        body = (
            "Bonjour,\n\n"
            f"{intro_templates[variant]} "
            "Notre offre met en avant un tarif attractif, des conditions simplifiées et une réponse rapide.\n\n"
            f"{cta_templates[variant]}\n\n"
            "À très vite,\n"
            "Service commercial"
        )
        return subject_templates[variant], body

    @classmethod
    def _build_repaired_spam(cls, source_preview: str) -> tuple[str, str]:
        amount = cls._extract_bonus_amount(source_preview) or "1 000 €"
        spins = cls._extract_spin_count(source_preview) or "100 tours gratuits"
        subject = f"Bonus de bienvenue {amount} + {spins}"
        body = (
            "Bonjour,\n\n"
            f"Votre offre de bienvenue est prête : jusqu'à {amount} de bonus et {spins} sont disponibles pour toute activation immédiate. "
            "Cette proposition est limitée et réservée aux nouveaux inscrits.\n\n"
            "Validez votre demande aujourd'hui pour débloquer votre avantage et recevoir les détails de participation sans attendre.\n\n"
            "Cordialement,\n"
            "Service avantages"
        )
        return subject, body

    @classmethod
    def _build_phishing_draft(cls, source_preview: str) -> tuple[str, str]:
        return (
            "Action requise pour confirmer votre accès",
            "Bonjour,\n\nUne vérification de sécurité est en attente sur votre espace et doit être traitée sans délai pour éviter une restriction temporaire de votre accès.\n\nVeuillez confirmer vos informations depuis la procédure indiquée et finaliser la vérification aujourd'hui.\n\nCordialement,\nService sécurité",
        )

    @classmethod
    def _build_generic_rewrite(
        cls,
        source_preview: str,
        job: dict[str, Any],
    ) -> tuple[str, str]:
        target_label = str(job.get("target_label") or "unknown")
        match target_label:
            case "legitimate":
                return cls._build_legitimate_notification(source_preview)
            case "spam":
                return cls._build_promotional_spam(source_preview)
            case "phishing":
                return cls._build_phishing_draft(source_preview)
            case _:
                return (
                    "Message reformulé à vérifier",
                    "Bonjour,\n\nCe brouillon nécessite une validation manuelle avant toute utilisation downstream.\n\nCordialement,\nRevue stage-two",
                )

    @staticmethod
    def _infer_promotional_topic(source_preview: str) -> str:
        lowered = source_preview.lower()
        topic_map = (
            ("assurance santé", "Assurance santé à prix avantageux"),
            ("protection juridique", "Protection juridique"),
            ("regroupement de crédit", "Regroupement de crédits"),
            ("cashback", "Programme cashback"),
            ("cagnotte", "Cagnotte fidélité"),
            ("voyager moins cher", "Voyage à prix réduit"),
            ("e-carte bleue", "Service e-Carte Bleue"),
            ("prêt immobilier", "Prêt immobilier"),
            ("assurance auto", "Assurance auto"),
            ("crédit", "Financement simplifié"),
            ("assurance", "Assurance personnalisée"),
        )
        for marker, topic in topic_map:
            if marker in lowered:
                return topic
        return StageTwoRewriteDraftService._extract_topic_phrase(
            source_preview,
            fallback="Offre exclusive réservée à votre profil",
        )

    @classmethod
    def _infer_legitimate_focus(cls, source_preview: str) -> str:
        lowered = source_preview.lower()
        focus_map = (
            (("réseaux sociaux", "internet"), "vos échanges sur Internet"),
            (
                ("fraude", "opération frauduleuse"),
                "la prévention des opérations frauduleuses",
            ),
            (("données bancaires",), "la protection de vos données bancaires"),
            (("mot de passe", "connexion", "accès"), "votre accès en ligne"),
            (("relevé", "document"), "vos documents mis à disposition"),
            (("paiement", "carte"), "vos paiements par carte"),
            (("certicode", "code à usage unique"), "l'authentification renforcée"),
        )
        for markers, focus in focus_map:
            if any(marker in lowered for marker in markers):
                return focus
        return cls._extract_topic_phrase(source_preview, fallback="votre espace client")

    @staticmethod
    def _extract_topic_phrase(source_preview: str, *, fallback: str) -> str:
        cleaned_preview = re.sub(r"\s+", " ", source_preview).strip()
        cleaned_preview = re.sub(
            r"(?i)accès à vos comptes par l'écran de connexion pleine page|accéder au menu principal|accéder au contenu éditorial|accéder au pied de page",
            " ",
            cleaned_preview,
        )
        candidates = [
            candidate.strip(" :-")
            for candidate in re.split(r"[.!?\n]+", cleaned_preview)
            if candidate.strip()
        ]
        for candidate in candidates:
            candidate = re.sub(r"^\d+\s*[-:]\s*", "", candidate)
            if len(candidate) < 18:
                continue
            words = candidate.split()
            phrase = " ".join(words[:6]).strip(" ,;:-")
            if len(phrase) >= 12:
                return phrase[0].upper() + phrase[1:]
        return fallback

    @staticmethod
    def _variant_index(seed: str, modulo: int) -> int:
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % modulo

    @staticmethod
    def _extract_bonus_amount(source_preview: str) -> str | None:
        patterns = (
            (r"€\s*(\d[\d\s]*(?:[,.]\d+)?)", "€"),
            (r"(\d[\d\s]*(?:[,.]\d+)?)\s*€", "€"),
            (r"\$\s*(\d[\d\s]*(?:[,.]\d+)?)", "$"),
            (r"(\d[\d\s]*(?:[,.]\d+)?)\s*\$", "$"),
        )
        for pattern, currency in patterns:
            if match := re.search(pattern, source_preview):
                return f"{match.group(1).strip()} {currency}"
        return None

    @staticmethod
    def _extract_spin_count(source_preview: str) -> str | None:
        if match := re.search(
            r"(\d+)\s*(?:free\s+spins|tours?\s+gratuits?)",
            source_preview,
            flags=re.IGNORECASE,
        ):
            return f"{match.group(1)} tours gratuits"
        return None

    @classmethod
    def _assess_draft(
        cls,
        *,
        job: dict[str, Any],
        source_preview: str,
        subject: str,
        body: str,
        full_text: str,
    ) -> tuple[str, list[str], dict[str, Any]]:
        lowered = full_text.lower()
        french_marker_count = len(
            [marker for marker in cls.FRENCH_MARKERS if marker in lowered]
        )
        mojibake_hits = sum(full_text.count(marker) for marker in cls.MOJIBAKE_MARKERS)
        target_label = str(job.get("target_label") or "unknown")
        target_cue_hits = len(
            [
                marker
                for marker in cls.TARGET_CUES.get(target_label, ())
                if marker in lowered
            ]
        )
        similarity_to_source = (
            round(
                SequenceMatcher(
                    None, source_preview.lower(), full_text.lower()
                ).ratio(),
                3,
            )
            if source_preview
            else None
        )

        review_notes: list[str] = []
        if len(source_preview) < 40:
            review_notes.append("insufficient_source_context")
        if mojibake_hits > 0:
            review_notes.append("residual_mojibake_detected")
        if french_marker_count < 3:
            review_notes.append("weak_french_framing")
        if target_cue_hits == 0:
            review_notes.append("weak_target_alignment")
        if len(body) < 120:
            review_notes.append("body_too_short_for_review")
        if len(body) > 1_500:
            review_notes.append("body_too_long_for_review")
        if similarity_to_source is not None and similarity_to_source > 0.82:
            review_notes.append("rewrite_too_close_to_source")

        if {
            "insufficient_source_context",
            "residual_mojibake_detected",
        }.intersection(
            review_notes
        ) and len(body) < 120:
            review_state = "drop"
        elif review_notes:
            review_state = "needs_prompt_tuning"
        else:
            review_state = "usable"

        quality_signals = {
            "subject_length": len(subject),
            "body_length": len(body),
            "french_marker_count": french_marker_count,
            "target_cue_hits": target_cue_hits,
            "mojibake_hits": mojibake_hits,
            "similarity_to_source": similarity_to_source,
        }
        return review_state, review_notes, quality_signals

    @staticmethod
    def _apply_duplicate_review_flags(drafts: list[dict[str, Any]]) -> None:
        hash_counts = Counter(str(draft.get("text_sha256") or "") for draft in drafts)
        for draft in drafts:
            draft_hash = str(draft.get("text_sha256") or "")
            if not draft_hash or hash_counts[draft_hash] <= 1:
                continue
            review_notes = list(draft.get("review_notes") or [])
            if "duplicate_generated_draft" not in review_notes:
                review_notes.append("duplicate_generated_draft")
            draft["review_notes"] = review_notes
            if draft.get("review_state") != "drop":
                draft["review_state"] = "needs_prompt_tuning"
