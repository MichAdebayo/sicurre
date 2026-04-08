from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
import re
from typing import Any

from data_platform.cleaning.normalization import clean_text, text_sha256


class CertFRGeneratedDraftService:
    IOC_LEAK_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"https?://", re.IGNORECASE),
        re.compile(r"\[url\]", re.IGNORECASE),
        re.compile(r"\bwww\.", re.IGNORECASE),
        re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    )
    FRENCH_MARKERS: tuple[str, ...] = (
        "bonjour",
        "veuillez",
        "vous",
        "votre",
        "compte",
        "document",
        "accès",
        "confirmer",
        "sécurité",
        "urgence",
    )
    PHISHING_CUES: tuple[str, ...] = (
        "action requise",
        "confirmer",
        "vérification",
        "sans délai",
        "restriction",
        "document",
        "accès",
        "connexion",
        "consulter",
        "ouvrir",
        "accéder",
    )
    SAFE_LINK_TOKEN_PREFIX = "[LIEN_"
    CTA_INSERTION_MODES: tuple[str, ...] = (
        "after_opening",
        "after_context",
        "append_opening",
        "prepend_pressure",
    )
    CTA_LIBRARY: dict[str, tuple[str, ...]] = {
        "banking_malware": (
            "Vous pouvez valider l'opération depuis [LIEN_VALIDATION_PAIEMENT].",
            "Le document reste accessible pour contrôle via [LIEN_PIECE_PAIEMENT].",
            "Pour confirmer le règlement, ouvrez [LIEN_CONFIRMATION_VIREMENT].",
        ),
        "credential_theft": (
            "Veuillez vérifier votre accès depuis [LIEN_VERIFICATION_COMPTE].",
            "La confirmation de votre session reste disponible via [LIEN_MAINTIEN_ACCES].",
            "Pour conserver l'accès, accédez à [LIEN_CONFIRMATION_IDENTIFIANTS].",
        ),
        "phishing": (
            "Veuillez confirmer votre accès sécurisé via [LIEN_CONFIRMATION_ACCES].",
            "Vous pouvez confirmer votre compte et maintenir votre accès en ouvrant [LIEN_MAINTIEN_COMPTE].",
            "Pour la vérification de sécurité de votre accès, consultez [LIEN_VERIFICATION_SERVICE].",
        ),
        "ransomware": (
            "Le document prioritaire peut être consulté depuis [LIEN_INCIDENT_PRIORITAIRE].",
            "Pour ouvrir le document transmis sans délai, consultez [LIEN_NOTE_URGENCE].",
            "Pour consulter la pièce d'incident et ouvrir le document de coordination, utilisez [LIEN_DOCUMENT_COORDINATION].",
        ),
        "generic_campaign": (
            "Une action requise reste accessible via [LIEN_DOSSIER_URGENT].",
            "Pour consulter la demande en attente sans délai, ouvrez [LIEN_DOCUMENT_PARTAGE].",
            "Vous pouvez confirmer la prise en charge du document depuis [LIEN_REPONSE_ATTENDUE].",
        ),
    }
    THEME_SENTENCE_LIBRARY: dict[str, dict[str, tuple[str, ...]]] = {
        "banking_malware": {
            "opening": (
                "Un document lié à un paiement en attente nécessite votre vérification avant clôture du traitement.",
                "Un document relatif à une opération de règlement reste en attente de validation dans votre dossier et vous devez le consulter rapidement.",
                "Le traitement d'un document de paiement transmis à votre service demande une vérification rapide.",
            ),
            "context": (
                "Veuillez consulter le document transmis et confirmer l'opération dans les meilleurs délais afin d'éviter un blocage de dossier.",
                "Nous vous invitons à consulter le document associé et à confirmer le contrôle avant validation comptable définitive.",
                "Veuillez confirmer ce document afin que votre demande soit finalisée sans report administratif.",
            ),
            "pressure": (
                "Une absence de retour aujourd'hui peut entraîner un report automatique.",
                "Sans confirmation rapide, le traitement sera suspendu jusqu'à nouvel avis.",
                "Le dossier risque d'être décalé si aucun retour n'est enregistré dans la journée.",
            ),
            "signature": (
                "Service comptabilité",
                "Cellule règlements",
            ),
        },
        "credential_theft": {
            "opening": (
                "Une anomalie a été détectée lors d'une tentative de connexion sur votre espace professionnel.",
                "Un contrôle inhabituel a été déclenché sur votre accès professionnel après une activité de connexion non reconnue.",
                "Votre espace de travail a fait l'objet d'une vérification de sécurité à la suite d'une connexion inhabituelle.",
            ),
            "context": (
                "Veuillez confirmer vos identifiants et vérifier votre accès sans délai pour éviter une restriction temporaire de votre compte.",
                "Merci de vérifier vos informations d'accès et de confirmer votre accès afin de maintenir la continuité de votre session.",
                "Cette vérification permet de confirmer que votre compte n'a pas été utilisé par un tiers.",
            ),
            "pressure": (
                "Vous devez confirmer cette étape de sécurité aujourd'hui pour maintenir votre accès.",
                "À défaut de validation, certaines fonctions de votre compte pourront être limitées temporairement.",
                "Une absence d'action rapide peut entraîner un verrouillage préventif de votre session.",
            ),
            "signature": (
                "Support sécurité",
                "Assistance accès",
            ),
        },
        "phishing": {
            "opening": (
                "Dans le cadre d'une vérification de sécurité, nous vous demandons de confirmer les informations liées à votre accès.",
                "Une procédure de vérification impose aujourd'hui de confirmer les informations associées à votre compte et à votre accès.",
                "Votre compte fait actuellement l'objet d'une vérification de sécurité et d'un contrôle d'accès avant maintien du service.",
            ),
            "context": (
                "Merci d'effectuer cette vérification et de confirmer votre accès dès réception afin d'éviter toute interruption de service.",
                "Veuillez confirmer votre accès afin de garantir la continuité de votre compte sans mesure de restriction.",
                "La validation demandée nous permet de maintenir votre accès et votre compte sans restriction dans les conditions habituelles.",
            ),
            "pressure": (
                "Sans confirmer votre accès sans délai, votre compte pourra faire l'objet d'une restriction préventive.",
                "Vous devez confirmer votre accès sans délai pour éviter une suspension temporaire de certaines fonctions de votre compte.",
                "Vous devez confirmer cette vérification de sécurité sans délai pour maintenir votre accès aujourd'hui.",
            ),
            "signature": (
                "Équipe assistance",
                "Service vérification",
            ),
        },
        "ransomware": {
            "opening": (
                "Un document lié à un incident opérationnel a été préparé pour votre service et doit être consulté sans délai.",
                "Un document d'urgence relatif à un incident affectant votre périmètre vient d'être mis à disposition et doit être consulté sans délai.",
                "Un document de coordination concernant un incident prioritaire attend votre retour et doit être consulté rapidement.",
            ),
            "context": (
                "Veuillez prendre connaissance du document transmis et confirmer votre lecture sans délai pour permettre la suite du traitement.",
                "Veuillez consulter cette note et confirmer la prise en charge côté service sans délai.",
                "Vous devez consulter et ouvrir ce document rapidement pour que la coordination puisse se poursuivre sans retard.",
            ),
            "pressure": (
                "Ce point est considéré comme prioritaire et vous devez ouvrir le document puis confirmer votre retour dans la journée.",
                "Sans ouvrir le document rapidement, le traitement de l'incident sera retardé pour votre équipe.",
                "Vous devez consulter le document et confirmer votre retour aujourd'hui afin d'éviter une escalade complémentaire.",
            ),
            "signature": (
                "Cellule coordination",
                "Pôle incident",
            ),
        },
        "generic_campaign": {
            "opening": (
                "Un élément vous concernant vient d'être déposé pour revue et nécessite une action de votre part.",
                "Une demande en attente de traitement a été rattachée à votre dossier ce matin et requiert une action rapide sur votre document.",
                "Un document transmis à votre attention requiert une vérification et une action requise avant clôture du suivi.",
            ),
            "context": (
                "Merci de consulter le document transmis et de confirmer votre prise en charge avant expiration du délai indiqué.",
                "Nous vous invitons à consulter le contenu reçu et à confirmer la demande en cours sans délai.",
                "La consultation de ce document est nécessaire pour poursuivre le traitement du dossier sans interruption et confirmer votre réponse.",
            ),
            "pressure": (
                "Sans consulter ce document et répondre rapidement, le dossier pourra être suspendu automatiquement.",
                "À défaut de retour aujourd'hui, la demande sera mise en attente par le système malgré l'action requise et la consultation sans délai attendue.",
                "Une absence de validation rapide risque de reporter le traitement à une date ultérieure.",
            ),
            "signature": (
                "Service suivi",
                "Cellule traitement",
            ),
        },
    }

    @classmethod
    def build_drafts(cls, synthesis_payload: dict[str, Any]) -> dict[str, Any]:
        drafts = [
            cls._build_draft(scenario)
            for scenario in synthesis_payload.get("scenarios", [])
        ]
        cls._apply_duplicate_review_flags(drafts)

        return {
            "mode": "certfr_generated_drafts",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "draft_count": len(drafts),
            "review_summary": dict(Counter(draft["review_state"] for draft in drafts)),
            "theme_summary": dict(
                Counter(str(draft["primary_theme"]) for draft in drafts)
            ),
            "family_summary": dict(
                Counter(str(draft["attack_family"]) for draft in drafts)
            ),
            "cta_position_summary": dict(
                Counter(
                    str(draft.get("quality_signals", {}).get("cta_position"))
                    for draft in drafts
                )
            ),
            "drafts": drafts,
        }

    @staticmethod
    def render_markdown(payload: dict[str, Any]) -> str:
        lines = [
            "# CERT-FR Generated Drafts",
            "",
            f"- Generated at: {payload.get('generated_at')}",
            f"- Draft count: {payload.get('draft_count')}",
            f"- Review summary: {payload.get('review_summary')}",
            f"- Theme summary: {payload.get('theme_summary')}",
            f"- Family summary: {payload.get('family_summary')}",
            f"- CTA position summary: {payload.get('cta_position_summary')}",
            "",
        ]

        for draft in payload.get("drafts", []):
            lines.extend(
                [
                    f"## {draft['draft_id']}",
                    "",
                    f"- Scenario id: {draft['scenario_id']}",
                    f"- Family: {draft['attack_family']}",
                    f"- Theme: {draft['primary_theme']}",
                    f"- Channel: {draft['delivery_channel']}",
                    f"- Review state: {draft['review_state']}",
                    f"- Review notes: {', '.join(draft.get('review_notes', [])) or 'none'}",
                    f"- CTA position: {draft.get('quality_signals', {}).get('cta_position')}",
                    f"- Quality signals: {draft.get('quality_signals')}",
                    "",
                    f"### Subject\n\n{draft['subject']}\n",
                    f"### Body\n\n{draft['body']}\n",
                ]
            )

        return "\n".join(lines)

    @classmethod
    def _build_draft(cls, scenario: dict[str, Any]) -> dict[str, Any]:
        variant_index = int(scenario.get("variant_index", 0) or 0)
        subject, body, cta_metadata = cls._generate_email(scenario)
        full_text = clean_text(f"Objet : {subject}\n\n{body}")
        review_state, review_notes, quality_signals = cls._assess_draft(
            scenario=scenario,
            subject=subject,
            body=body,
            full_text=full_text,
        )
        quality_signals.update(cta_metadata)

        return {
            "draft_id": str(scenario.get("scenario_id") or "unknown"),
            "scenario_id": scenario.get("scenario_id"),
            "source_name": "cert-fr-cti",
            "attack_family": scenario.get("attack_family"),
            "primary_theme": scenario.get("primary_theme"),
            "delivery_channel": scenario.get("delivery_channel"),
            "target_label": "phishing",
            "variant_index": variant_index,
            "seed_record_ids": scenario.get("sampled_record_ids", []),
            "review_state": review_state,
            "review_notes": review_notes,
            "quality_signals": quality_signals,
            "subject": subject,
            "body": body,
            "full_text": full_text,
            "text_sha256": text_sha256(full_text),
            "generation_constraints": scenario.get("generation_constraints", []),
            "prompt_brief": scenario.get("prompt_brief"),
            "lexical_cues": scenario.get("lexical_cues", []),
            "lure_focus": scenario.get("lure_focus"),
        }

    @classmethod
    def _generate_email(
        cls, scenario: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any]]:
        theme = str(scenario.get("primary_theme") or "generic_campaign")
        family = str(scenario.get("attack_family") or "generic")
        variant_index = int(scenario.get("variant_index", 0) or 0)
        scenario_id = (
            f"{str(scenario.get('scenario_id') or '')}:variant:{variant_index}"
        )
        match theme:
            case "banking_malware":
                return cls._build_banking_draft(scenario_id, family)
            case "credential_theft":
                return cls._build_credential_draft(scenario_id, family)
            case "phishing":
                return cls._build_account_verification_draft(scenario_id, family)
            case "ransomware":
                return cls._build_ransomware_lure_draft(scenario_id, family)
            case _:
                return cls._build_generic_campaign_draft(scenario_id, family)

    @classmethod
    def _build_banking_draft(
        cls,
        scenario_id: str,
        family: str,
    ) -> tuple[str, str, dict[str, Any]]:
        subject_map = {
            "dridex": "Document de paiement en attente de validation",
            "silence": "Confirmation requise sur votre opération bancaire",
        }
        subject = subject_map.get(family, "Facture à vérifier avant traitement")
        structure = cls._select_theme_structure("banking_malware", scenario_id)
        return cls._compose_email(
            scenario_id=scenario_id,
            theme="banking_malware",
            subject=subject,
            opening=structure["opening"],
            context=structure["context"],
            pressure=structure["pressure"],
            signature=structure["signature"],
        )

    @classmethod
    def _build_credential_draft(
        cls,
        scenario_id: str,
        family: str,
    ) -> tuple[str, str, dict[str, Any]]:
        del family
        subject = "Vérification nécessaire de vos identifiants professionnels"
        structure = cls._select_theme_structure("credential_theft", scenario_id)
        return cls._compose_email(
            scenario_id=scenario_id,
            theme="credential_theft",
            subject=subject,
            opening=structure["opening"],
            context=structure["context"],
            pressure=structure["pressure"],
            signature=structure["signature"],
        )

    @classmethod
    def _build_account_verification_draft(
        cls,
        scenario_id: str,
        family: str,
    ) -> tuple[str, str, dict[str, Any]]:
        del family
        subject = "Vérification requise pour confirmer votre accès"
        structure = cls._select_theme_structure("phishing", scenario_id)
        return cls._compose_email(
            scenario_id=scenario_id,
            theme="phishing",
            subject=subject,
            opening=structure["opening"],
            context=structure["context"],
            pressure=structure["pressure"],
            signature=structure["signature"],
        )

    @classmethod
    def _build_ransomware_lure_draft(
        cls,
        scenario_id: str,
        family: str,
    ) -> tuple[str, str, dict[str, Any]]:
        subject_map = {
            "maze": "Analyse urgente d'un incident à consulter",
            "ryuk": "Document d'urgence à consulter aujourd'hui",
        }
        subject = subject_map.get(family, "Document prioritaire à ouvrir aujourd'hui")
        structure = cls._select_theme_structure("ransomware", scenario_id)
        return cls._compose_email(
            scenario_id=scenario_id,
            theme="ransomware",
            subject=subject,
            opening=structure["opening"],
            context=structure["context"],
            pressure=structure["pressure"],
            signature=structure["signature"],
        )

    @classmethod
    def _build_generic_campaign_draft(
        cls,
        scenario_id: str,
        family: str,
    ) -> tuple[str, str, dict[str, Any]]:
        subject_map = {
            "emotet": "Action requise sur un document partagé",
            "ta505": "Réponse attendue sur votre dossier transmis",
        }
        subject = subject_map.get(family, "Action requise sur votre dossier")
        structure = cls._select_theme_structure("generic_campaign", scenario_id)
        return cls._compose_email(
            scenario_id=scenario_id,
            theme="generic_campaign",
            subject=subject,
            opening=structure["opening"],
            context=structure["context"],
            pressure=structure["pressure"],
            signature=structure["signature"],
        )

    @classmethod
    def _select_theme_structure(
        cls,
        theme: str,
        scenario_id: str,
    ) -> dict[str, str]:
        theme_library = cls.THEME_SENTENCE_LIBRARY.get(
            theme,
            cls.THEME_SENTENCE_LIBRARY["generic_campaign"],
        )
        return {
            component: options[
                cls._deterministic_index(
                    f"{scenario_id}:{theme}:{component}",
                    len(options),
                )
            ]
            for component, options in theme_library.items()
        }

    @classmethod
    def _compose_email(
        cls,
        *,
        scenario_id: str,
        theme: str,
        subject: str,
        opening: str,
        context: str,
        pressure: str,
        signature: str,
    ) -> tuple[str, str, dict[str, Any]]:
        cta_options = cls.CTA_LIBRARY.get(theme, cls.CTA_LIBRARY["generic_campaign"])
        cta_sentence = cta_options[
            cls._deterministic_index(f"{scenario_id}:{theme}:cta", len(cta_options))
        ]
        cta_position = cls.CTA_INSERTION_MODES[
            cls._deterministic_index(
                f"{scenario_id}:{theme}:position",
                len(cls.CTA_INSERTION_MODES),
            )
        ]

        paragraphs = [opening, context, pressure]
        match cta_position:
            case "after_opening":
                paragraphs = [opening, cta_sentence, context, pressure]
            case "after_context":
                paragraphs = [opening, context, cta_sentence, pressure]
            case "append_opening":
                paragraphs = [f"{opening} {cta_sentence}", context, pressure]
            case "prepend_pressure":
                paragraphs = [opening, context, f"{cta_sentence} {pressure}"]

        body = (
            "Bonjour,\n\n" + "\n\n".join(paragraphs) + "\n\nCordialement,\n" + signature
        )
        return (
            subject,
            body,
            {
                "cta_position": cta_position,
                "cta_variant": cta_sentence,
                "structure_opening": opening,
                "structure_context": context,
                "structure_pressure": pressure,
                "structure_signature": signature,
            },
        )

    @staticmethod
    def _deterministic_index(seed: str, modulo: int) -> int:
        return 0 if modulo <= 0 else int(text_sha256(seed)[:8], 16) % modulo

    @classmethod
    def _assess_draft(
        cls,
        *,
        scenario: dict[str, Any],
        subject: str,
        body: str,
        full_text: str,
    ) -> tuple[str, list[str], dict[str, Any]]:
        lowered = full_text.lower()
        french_marker_count = len(
            [marker for marker in cls.FRENCH_MARKERS if marker in lowered]
        )
        phishing_cue_hits = len(
            [marker for marker in cls.PHISHING_CUES if marker in lowered]
        )
        cta_present = cls.SAFE_LINK_TOKEN_PREFIX.lower() in lowered
        prompt_brief = str(scenario.get("prompt_brief") or "")
        similarity_to_prompt = (
            round(
                SequenceMatcher(None, prompt_brief.lower(), full_text.lower()).ratio(),
                3,
            )
            if prompt_brief
            else None
        )

        review_notes: list[str] = []
        if french_marker_count < 4:
            review_notes.append("weak_french_framing")
        if phishing_cue_hits < 3:
            review_notes.append("weak_phishing_signals")
        if len(body) < 140:
            review_notes.append("body_too_short_for_review")
        if not cta_present:
            review_notes.append("missing_action_cta")
        if any(pattern.search(full_text) for pattern in cls.IOC_LEAK_PATTERNS):
            review_notes.append("possible_ioc_leak")
        if similarity_to_prompt is not None and similarity_to_prompt > 0.82:
            review_notes.append("draft_too_close_to_prompt_brief")

        if "possible_ioc_leak" in review_notes:
            review_state = "drop"
        elif review_notes:
            review_state = "needs_prompt_tuning"
        else:
            review_state = "usable"

        quality_signals = {
            "subject_length": len(subject),
            "body_length": len(body),
            "french_marker_count": french_marker_count,
            "phishing_cue_hits": phishing_cue_hits,
            "cta_present": cta_present,
            "similarity_to_prompt": similarity_to_prompt,
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
