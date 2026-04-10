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
    LEGITIMATE_TOPIC_KEYWORDS: tuple[str, ...] = (
        "notification",
        "notifications",
        "virement",
        "sms",
        "paiement",
        "paiements",
        "carte",
        "sécurité",
        "fraude",
        "frauduleux",
        "données bancaires",
        "document",
        "relevé",
        "mot de passe",
        "accès",
        "compte",
        "certicode",
        "appel",
        "e-carte bleue",
        "messagerie sécurisée",
        "apple pay",
        "samsung pay",
    )
    BAD_TOPIC_PREFIXES: tuple[str, ...] = (
        "selon les conditions générales",
        "en outre",
        "en second lieu",
        "conformément",
        "télécharger",
        "tous les champs",
        "les 3 modes",
        "identifier facilement",
        "étape ",
        "etape ",
        "historique des remises",
        "services digitaux",
        "gestion compte bancaire",
        "nos services",
        "des intérêts débiteurs",
        "# paiement",
        "service e-carte bleue",
    )
    BAD_TOPIC_SUBSTRINGS: tuple[str, ...] = (
        "menu principal",
        "contenu éditorial",
        "pied de page",
        "tous les champs sont obligatoires",
        "notice d'information",
        "l’organisateur se réserve",
        "l'organisateur se réserve",
        "conformément à cette dernière exigence réglementaire",
        "actuellement nous travaillons",
        "rapprochez-vous de votre conseiller habituel",
        "[phone]service",
    )
    PAGE_LIKE_SUBJECT_MARKERS: tuple[str, ...] = (
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
    NOISY_TOPIC_MARKERS: tuple[str, ...] = (
        "ensemble contre les arnaques",
        "signaler une arnaque",
        "s'inscrire à la newsletter",
        "alertes du moment",
        "sujets les plus consultés",
        "arnaques classées par catégories",
        "en savoir +",
        "up vote down vote",
        "commentaire / explications",
        "contenu de l'arnaque",
        "créer un groupe prive",
        "creer un groupe prive",
        "les avis et commentaires laissés par les internautes",
        "les avis et commentaires laisses par les internautes",
        "répondre ajouter une image",
        "repondre ajouter une image",
        "laisser une réponse",
        "laisser une reponse",
        "etre notifié des nouveaux commentaires",
        "etre notifie des nouveaux commentaires",
    )
    PROMOTIONAL_TOPIC_KEYWORDS: tuple[str, ...] = (
        "prêt relais",
        "pret relais",
        "crédit renouvelable",
        "credit renouvelable",
        "microcrédit personnel",
        "microcredit personnel",
        "assurance habitation",
        "assurance santé",
        "assurance auto",
        "protection juridique",
        "prêt personnel",
        "prêt immobilier",
        "open payment",
        "lettre chèque",
        "lettre cheque",
        "paiement sans contact",
        "visa premier",
        "tarifs bancaires",
        "nvei",
        "camping-car",
        "camping-cars",
        "regroupement de crédit",
        "regroupement de credits",
        "cashback",
        "cagnotte",
        "e-carte bleue",
        "paiement",
        "carte bancaire",
        "financement",
        "crédit",
        "credit",
        "voyage",
        "livret",
        "épargne",
        "epargne",
        "responsabilité civile",
        "responsabilite civile",
        "garanties",
    )
    GENERIC_LEGITIMATE_SUBJECT_PREFIXES: tuple[str, ...] = (
        "information utile concernant",
        "rappel pratique au sujet de",
        "point d'information pour",
        "mise au point utile concernant",
    )
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
                return cls._build_instructional_notification(source_preview)
            case "awareness_page_to_warning_notification":
                return cls._build_awareness_notification(source_preview)
            case "promotional_page_to_spam_message":
                return cls._build_promotional_spam(source_preview)
            case "repair_then_rewrite":
                return cls._build_repaired_spam(source_preview)
            case "embedded_lure_to_phishing_email":
                return cls._build_phishing_draft(job, source_preview)
            case _:
                return cls._build_generic_rewrite(source_preview, job)

    @classmethod
    def _build_instructional_notification(cls, source_preview: str) -> tuple[str, str]:
        lowered = source_preview.lower()
        if any(
            marker in lowered
            for marker in (
                "fraude",
                "frauduleux",
                "douteux",
                "ne communiquez jamais",
                "appel suspect",
            )
        ):
            return cls._build_vigilance_notification(source_preview)
        if any(
            marker in lowered
            for marker in (
                "notification",
                "notifications",
                "virement",
                "sms",
                "apple pay",
                "samsung pay",
                "messagerie sécurisée",
                "e-carte bleue",
            )
        ):
            return cls._build_payment_notification(source_preview)
        if any(
            marker in lowered
            for marker in (
                "mot de passe",
                "connexion",
                "accès",
                "certicode",
                "code à usage unique",
                "espace client",
            )
        ):
            return cls._build_access_security_notification(source_preview)
        if any(
            marker in lowered
            for marker in ("document", "relevé", "notice", "télécharger")
        ):
            return cls._build_document_notification(source_preview)
        return cls._build_general_legitimate_notification(source_preview)

    @classmethod
    def _build_payment_notification(cls, source_preview: str) -> tuple[str, str]:
        lowered = source_preview.lower()
        focus = cls._extract_legitimate_topic(
            source_preview,
            fallback=cls._infer_legitimate_focus(source_preview),
        )
        variant = cls._variant_index(source_preview, 4)
        subjects = (
            f"Point d'information sur {focus.lower()}",
            f"Rappel utile concernant {focus.lower()}",
            f"Notification liée à {focus.lower()}",
            f"Mise à jour utile pour {focus.lower()}",
        )
        bodies = (
            f"Bonjour,\n\nNous vous rappelons que les opérations liées à {focus.lower()} doivent être consultées uniquement depuis vos canaux habituels.\n\nSelon votre situation, vous pouvez recevoir une information par SMS, notification ou messagerie sécurisée. En cas de doute, vérifiez toujours la demande depuis votre espace client.\n\nCordialement,\nVotre service client",
            f"Bonjour,\n\nCe message vous rappelle les bons réflexes à adopter pour {focus.lower()} et les notifications associées.\n\nAvant toute validation sensible, contrôlez la demande depuis votre environnement habituel et ne partagez jamais d'informations confidentielles en réponse à un message inattendu.\n\nCordialement,\nVotre service client",
            f"Bonjour,\n\nPour toute démarche relative à {focus.lower()}, utilisez uniquement les notifications et parcours disponibles dans votre espace habituel.\n\nSi une demande paraît inhabituelle, interrompez l'action et rapprochez-vous de votre service client avant toute saisie d'information.\n\nCordialement,\nVotre service client",
            f"Bonjour,\n\nNous vous invitons à vérifier avec attention toute alerte reçue au sujet de {focus.lower()}.\n\nLes confirmations sensibles doivent toujours être traitées depuis vos canaux officiels, sans passer par un lien ou un message inattendu.\n\nCordialement,\nVotre service client",
        )
        return subjects[variant], bodies[variant]

    @classmethod
    def _build_access_security_notification(
        cls, source_preview: str
    ) -> tuple[str, str]:
        focus = cls._extract_legitimate_topic(
            source_preview,
            fallback=cls._infer_legitimate_focus(source_preview),
        )
        variant = cls._variant_index(source_preview, 4)
        subjects = (
            f"Information sur la sécurisation de {focus.lower()}",
            f"Mise à jour utile concernant {focus.lower()}",
            f"Conseils de sécurité pour {focus.lower()}",
            f"Point de contrôle lié à {focus.lower()}",
        )
        bodies = (
            f"Bonjour,\n\nSi vous devez réinitialiser {focus.lower()}, suivez uniquement les étapes disponibles depuis votre espace habituel.\n\nSelon votre situation, un code temporaire pourra vous être transmis par SMS ou par courrier. En cas de doute, contactez votre conseiller avant toute saisie d'information.\n\nCordialement,\nVotre service client",
            f"Bonjour,\n\nPour toute action portant sur {focus.lower()}, utilisez exclusivement vos parcours de connexion et de validation habituels.\n\nN'acceptez jamais une demande urgente sans avoir confirmé son origine via vos canaux officiels.\n\nCordialement,\nVotre service client",
            f"Bonjour,\n\nNous vous rappelons que les vérifications liées à {focus.lower()} doivent être traitées uniquement depuis votre espace habituel.\n\nSi un code ou une demande de confirmation vous paraît inattendu, interrompez la procédure et rapprochez-vous de votre service client.\n\nCordialement,\nVotre service client",
            f"Bonjour,\n\nCe message rappelle les bonnes pratiques de sécurité à suivre pour {focus.lower()}.\n\nAvant toute saisie d'information, contrôlez toujours l'origine de la demande et privilégiez un accès direct à votre espace personnel.\n\nCordialement,\nVotre service client",
        )
        return subjects[variant], bodies[variant]

    @classmethod
    def _build_document_notification(cls, source_preview: str) -> tuple[str, str]:
        focus = cls._extract_legitimate_topic(
            source_preview,
            fallback="vos documents disponibles",
        )
        variant = cls._variant_index(source_preview, 4)
        subjects = (
            f"Information utile concernant {focus.lower()}",
            f"Rappel pratique au sujet de {focus.lower()}",
            f"Mise à disposition liée à {focus.lower()}",
            f"Point d'information pour {focus.lower()}",
        )
        bodies = (
            f"Bonjour,\n\nNous vous informons que les éléments relatifs à {focus.lower()} doivent être consultés depuis vos espaces habituels et sécurisés.\n\nEn cas de doute sur un document reçu ou annoncé, connectez-vous directement à votre espace client avant toute action.\n\nCordialement,\nVotre service client",
            f"Bonjour,\n\nCe rappel concerne {focus.lower()} et les vérifications utiles avant toute consultation ou téléchargement.\n\nN'utilisez que vos canaux officiels pour accéder à vos documents et contactez votre service client si une demande vous semble inhabituelle.\n\nCordialement,\nVotre service client",
            f"Bonjour,\n\nPour toute consultation liée à {focus.lower()}, privilégiez un accès direct à votre espace habituel.\n\nSi un message vous demande d'agir en urgence sur un document ou un relevé, vérifiez d'abord sa légitimité.\n\nCordialement,\nVotre service client",
            f"Bonjour,\n\nNous vous invitons à vérifier avec attention les notifications portant sur {focus.lower()}.\n\nAvant d'ouvrir un document ou de suivre une consigne, assurez-vous que la demande provient bien de vos canaux officiels.\n\nCordialement,\nVotre service client",
        )
        return subjects[variant], bodies[variant]

    @classmethod
    def _build_vigilance_notification(cls, source_preview: str) -> tuple[str, str]:
        focus = cls._extract_legitimate_topic(
            source_preview,
            fallback=cls._infer_legitimate_focus(source_preview),
        )
        variant = cls._variant_index(source_preview, 4)
        subjects = (
            f"Rappel de vigilance concernant {focus}",
            f"Alerte de prudence au sujet de {focus}",
            f"Bonnes pratiques liées à {focus}",
            f"Sécurité renforcée pour {focus}",
        )
        bodies = (
            f"Bonjour,\n\nNous vous rappelons de ne jamais transmettre vos données bancaires, vos codes de validation ou vos informations personnelles lorsqu'un message inattendu évoque {focus.lower()}.\n\nEn cas de message douteux, connectez-vous uniquement à votre espace habituel ou rapprochez-vous de votre service client avant toute action.\n\nCordialement,\nVotre service client",
            f"Bonjour,\n\nDes sollicitations peuvent utiliser {focus.lower()} pour provoquer une réaction urgente.\n\nAvant toute réponse, vérifiez l'origine du contact via vos canaux habituels et ne communiquez aucune information sensible sans contrôle préalable.\n\nCordialement,\nVotre service client",
            f"Bonjour,\n\nCe message rappelle les bons réflexes à adopter lorsque {focus.lower()} est mentionné dans un e-mail, un SMS ou un appel inattendu.\n\nEn cas de doute, interrompez l'échange et rapprochez-vous directement de votre service client.\n\nCordialement,\nVotre service client",
            f"Bonjour,\n\nNous attirons votre attention sur les risques liés à {focus.lower()} lorsqu'une demande inhabituelle cherche à obtenir une action immédiate.\n\nNe cliquez pas sur un lien inattendu et privilégiez toujours un accès direct à votre espace personnel.\n\nCordialement,\nVotre service client",
        )
        return subjects[variant], bodies[variant]

    @classmethod
    def _build_general_legitimate_notification(
        cls, source_preview: str
    ) -> tuple[str, str]:
        focus = cls._extract_legitimate_topic(
            source_preview,
            fallback=cls._infer_legitimate_focus(source_preview),
        )
        variant = cls._variant_index(source_preview, 4)
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
    def _build_awareness_notification(cls, source_preview: str) -> tuple[str, str]:
        focus = cls._extract_legitimate_topic(
            source_preview,
            fallback=cls._infer_awareness_focus(source_preview),
        )
        channels = cls._describe_risk_channels(source_preview)
        action = cls._extract_warning_action(source_preview)
        variant = cls._variant_index(source_preview, 4)
        subjects = (
            f"Vigilance renforcée concernant {focus}",
            f"Rappel de prudence au sujet de {focus}",
            f"Conseils utiles concernant {focus}",
            f"Point de vigilance lié à {focus}",
        )
        bodies = (
            f"Bonjour,\n\nNous vous invitons à rester vigilant face aux sollicitations reçues {channels} lorsqu'elles mentionnent {focus.lower()}.\n\n{action}\n\nEn cas de doute, reconnectez-vous uniquement à votre espace habituel ou contactez directement votre service client.\n\nCordialement,\nVotre service client",
            f"Bonjour,\n\nCe rappel de prudence concerne les contacts inattendus reçus {channels} et portant sur {focus.lower()}.\n\n{action}\n\nSi une demande vous semble inhabituelle, interrompez l'échange et vérifiez son origine via vos canaux officiels.\n\nCordialement,\nVotre service client",
            f"Bonjour,\n\nNous attirons votre attention sur les sollicitations {channels} qui tentent de provoquer une réaction rapide en évoquant {focus.lower()}.\n\n{action}\n\nAvant toute validation, assurez-vous que la demande provient bien de vos canaux habituels.\n\nCordialement,\nVotre service client",
            f"Bonjour,\n\nCe message rappelle les vérifications utiles à effectuer lorsque {focus.lower()} est mentionné dans un message, un appel ou une notification inattendue.\n\n{action}\n\nPour toute situation ambiguë, privilégiez un accès direct à votre espace personnel ou un appel au service client.\n\nCordialement,\nVotre service client",
        )
        return subjects[variant], bodies[variant]

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
    def _build_phishing_draft(
        cls,
        job: dict[str, Any],
        source_preview: str,
    ) -> tuple[str, str]:
        del job
        theme = cls._infer_phishing_theme(source_preview)
        entity = cls._infer_phishing_entity(source_preview, theme=theme)
        reference = cls._build_phishing_reference(source_preview, theme=theme)
        variant = cls._variant_index(source_preview, 4)

        match theme:
            case "delivery":
                subjects = (
                    f"{entity} : confirmation requise pour votre livraison {reference}",
                    f"{entity} : votre colis reste en attente aujourd'hui",
                    f"{entity} : dernière étape avant remise du colis {reference}",
                    f"{entity} : régularisation nécessaire avant nouvelle livraison",
                )
                bodies = (
                    "Bonjour,\n\n"
                    f"Votre colis référencé {reference} n'a pas pu être remis ce matin. Une vérification de vos coordonnées est attendue sans délai afin d'éviter le retour du pli au centre de distribution.\n\n"
                    "Veuillez confirmer votre créneau de livraison et finaliser la procédure aujourd'hui depuis le formulaire sécurisé mis à votre disposition.\n\n"
                    f"Cordialement,\n{entity}",
                    "Bonjour,\n\n"
                    f"Une tentative de livraison liée au dossier {reference} reste suspendue après un échec de remise. Pour maintenir l'acheminement, nous vous demandons de confirmer votre adresse et vos informations de réception sans délai.\n\n"
                    "Merci d'effectuer la vérification demandée aujourd'hui afin d'éviter une suspension définitive de la distribution.\n\n"
                    f"Cordialement,\n{entity}",
                    "Bonjour,\n\n"
                    f"Votre expédition {reference} nécessite une action requise avant remise au point relais. Une confirmation de votre disponibilité est attendue aujourd'hui pour débloquer la livraison.\n\n"
                    "Veuillez vérifier les informations demandées et confirmer votre choix de remise depuis la procédure sécurisée prévue à cet effet.\n\n"
                    f"Cordialement,\n{entity}",
                    "Bonjour,\n\n"
                    f"Un complément d'information est nécessaire pour relancer la livraison du colis {reference}. Sans vérification de votre dossier aujourd'hui, l'envoi restera suspendu et sera retourné à l'expéditeur.\n\n"
                    "Merci de confirmer immédiatement vos informations de réception afin de finaliser la nouvelle présentation du colis.\n\n"
                    f"Cordialement,\n{entity}",
                )
            case "payment":
                subjects = (
                    f"{entity} : facture en attente de vérification {reference}",
                    f"{entity} : action requise pour confirmer votre règlement",
                    f"{entity} : document de paiement à valider aujourd'hui",
                    f"{entity} : suspension prévue sans vérification de votre dossier",
                )
                bodies = (
                    "Bonjour,\n\n"
                    f"Une facture liée au dossier {reference} n'a pas pu être traitée automatiquement. Une vérification de vos informations de paiement est requise sans délai afin d'éviter le blocage du traitement.\n\n"
                    "Veuillez confirmer votre règlement depuis la procédure indiquée et finaliser la validation aujourd'hui.\n\n"
                    f"Cordialement,\n{entity}",
                    "Bonjour,\n\n"
                    f"Nous avons détecté une anomalie sur le règlement associé à la référence {reference}. Votre dossier restera suspendu tant que la vérification demandée n'aura pas été confirmée.\n\n"
                    "Merci de confirmer immédiatement vos informations de paiement afin d'éviter une interruption de service.\n\n"
                    f"Cordialement,\n{entity}",
                    "Bonjour,\n\n"
                    f"Le document de paiement {reference} nécessite une action requise avant clôture. Une vérification de sécurité doit être effectuée aujourd'hui pour maintenir la prise en charge de votre dossier.\n\n"
                    "Veuillez confirmer votre accès et valider les informations demandées depuis le formulaire sécurisé.\n\n"
                    f"Cordialement,\n{entity}",
                    "Bonjour,\n\n"
                    f"Suite à un contrôle de routine, la référence {reference} doit être confirmée sans délai pour éviter une suspension automatique de votre dossier.\n\n"
                    "Merci de procéder à la vérification aujourd'hui et de confirmer votre règlement afin de lever l'alerte en cours.\n\n"
                    f"Cordialement,\n{entity}",
                )
            case "admin":
                subjects = (
                    f"{entity} : mise à jour obligatoire de votre dossier {reference}",
                    f"{entity} : vérification requise pour maintenir votre accès",
                    f"{entity} : confirmation attendue aujourd'hui sur votre espace",
                    f"{entity} : action immédiate nécessaire sur votre dossier",
                )
                bodies = (
                    "Bonjour,\n\n"
                    f"Une mise à jour liée à votre dossier {reference} doit être confirmée sans délai pour maintenir l'accès à votre espace personnel. Une vérification de vos informations est désormais requise.\n\n"
                    "Veuillez confirmer les éléments demandés aujourd'hui depuis la procédure sécurisée afin d'éviter une suspension temporaire de vos services.\n\n"
                    f"Cordialement,\n{entity}",
                    "Bonjour,\n\n"
                    f"Votre espace fait actuellement l'objet d'une vérification obligatoire concernant la référence {reference}. Sans confirmation aujourd'hui, votre dossier sera placé en attente de régularisation.\n\n"
                    "Merci de confirmer immédiatement vos informations depuis le formulaire indiqué pour maintenir votre accès.\n\n"
                    f"Cordialement,\n{entity}",
                    "Bonjour,\n\n"
                    f"Une action requise a été enregistrée sur le dossier {reference}. Afin d'éviter une suspension de traitement, nous vous demandons de vérifier votre identité et de confirmer votre accès sans délai.\n\n"
                    "Veuillez finaliser la procédure aujourd'hui pour maintenir vos services actifs.\n\n"
                    f"Cordialement,\n{entity}",
                    "Bonjour,\n\n"
                    f"Le maintien de votre dossier {reference} dépend d'une vérification immédiate de vos informations. À défaut de confirmation aujourd'hui, votre accès pourra être restreint temporairement.\n\n"
                    "Merci de procéder sans délai à la vérification requise via la procédure sécurisée mise à disposition.\n\n"
                    f"Cordialement,\n{entity}",
                )
            case _:
                subjects = (
                    f"{entity} : action requise pour confirmer votre accès {reference}",
                    f"{entity} : vérification de sécurité en attente aujourd'hui",
                    f"{entity} : suspension prévue sans confirmation de votre dossier",
                    f"{entity} : confirmation nécessaire pour maintenir votre accès",
                )
                bodies = (
                    "Bonjour,\n\n"
                    f"Une vérification de sécurité liée à la référence {reference} est en attente sur votre espace. Cette procédure doit être traitée sans délai afin d'éviter une restriction temporaire de votre accès.\n\n"
                    "Veuillez confirmer vos informations depuis la procédure indiquée et finaliser la vérification aujourd'hui.\n\n"
                    f"Cordialement,\n{entity}",
                    "Bonjour,\n\n"
                    f"Nous avons détecté une activité nécessitant la confirmation du dossier {reference}. Sans action requise de votre part aujourd'hui, votre accès restera suspendu à titre préventif.\n\n"
                    "Merci de confirmer immédiatement vos informations afin de finaliser la vérification de sécurité en cours.\n\n"
                    f"Cordialement,\n{entity}",
                    "Bonjour,\n\n"
                    f"Votre compte fait l'objet d'une vérification urgente portant sur la référence {reference}. Une confirmation sans délai est nécessaire pour éviter une suspension automatique des services associés.\n\n"
                    "Veuillez vérifier les informations demandées et confirmer votre accès depuis la procédure sécurisée prévue à cet effet.\n\n"
                    f"Cordialement,\n{entity}",
                    "Bonjour,\n\n"
                    f"Une action de contrôle a été déclenchée sur le dossier {reference}. Pour maintenir votre accès actif, nous vous demandons de confirmer les éléments de sécurité aujourd'hui.\n\n"
                    "Merci de procéder à la vérification demandée dès réception de ce message afin d'éviter toute interruption temporaire.\n\n"
                    f"Cordialement,\n{entity}",
                )

        return subjects[variant], bodies[variant]

    @staticmethod
    def _build_phishing_reference(source_preview: str, *, theme: str) -> str:
        prefix_map = {
            "delivery": "CL",
            "payment": "PAI",
            "admin": "DOS",
            "account": "ACC",
        }
        prefix = prefix_map.get(theme, "REF")
        digest = hashlib.sha256(source_preview.lower().encode("utf-8")).hexdigest()
        return f"{prefix}-{digest[:6].upper()}"

    @staticmethod
    def _infer_phishing_theme(source_preview: str) -> str:
        lowered = source_preview.lower()
        if any(
            marker in lowered
            for marker in (
                "mondial relay",
                "relay",
                "colis",
                "livraison",
                "coursier",
                "livreur",
                "distribution-retard",
                "relais",
            )
        ):
            return "delivery"
        if any(
            marker in lowered
            for marker in (
                "urssaf",
                "ameli",
                "impot",
                "impôts",
                "service public",
                "carte vitale",
                "caf",
                "cpam",
            )
        ):
            return "admin"
        if any(
            marker in lowered
            for marker in (
                "paiement",
                "facture",
                "carte",
                "bancaire",
                "virement",
                "douane",
                "règlement",
                "reglement",
            )
        ):
            return "payment"
        if any(
            marker in lowered
            for marker in (
                "compte",
                "accès",
                "acces",
                "connexion",
                "mot de passe",
                "espace client",
                "suspension",
            )
        ):
            return "account"
        return "account"

    @staticmethod
    def _infer_phishing_entity(source_preview: str, *, theme: str) -> str:
        lowered = source_preview.lower()
        entity_map = (
            ("mondial relay", "Mondial Relay"),
            ("chronopost", "Chronopost"),
            ("la poste", "La Poste"),
            ("laposte", "La Poste"),
            ("ameli", "Ameli"),
            ("urssaf", "URSSAF"),
            ("impot", "Service fiscal"),
            ("impôts", "Service fiscal"),
            ("service public", "Service Public"),
            ("caf", "CAF"),
            ("cpam", "Assurance Maladie"),
        )
        for marker, entity in entity_map:
            if marker in lowered:
                return entity
        match theme:
            case "delivery":
                return "Service livraison"
            case "payment":
                return "Service facturation"
            case "admin":
                return "Service dossier"
            case _:
                return "Service sécurité"

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
                return cls._build_phishing_draft(job, source_preview)
            case _:
                return (
                    "Message reformulé à vérifier",
                    "Bonjour,\n\nCe brouillon nécessite une validation manuelle avant toute utilisation downstream.\n\nCordialement,\nRevue stage-two",
                )

    @staticmethod
    def _infer_promotional_topic(source_preview: str) -> str:
        lowered = source_preview.lower()
        if topic := StageTwoRewriteDraftService._extract_promotional_topic(
            source_preview
        ):
            return topic
        topic_map = (
            ("prêt relais", "Prêt relais"),
            ("pret relais", "Prêt relais"),
            ("crédit renouvelable", "Crédit renouvelable"),
            ("credit renouvelable", "Crédit renouvelable"),
            ("microcrédit personnel", "Microcrédit personnel"),
            ("microcredit personnel", "Microcrédit personnel"),
            ("open payment", "Open Payment"),
            ("lettre chèque", "Lettre chèque"),
            ("lettre cheque", "Lettre chèque"),
            ("paiement sans contact", "Paiement sans contact"),
            ("visa premier", "Carte Visa Premier"),
            ("tarifs bancaires", "Tarifs bancaires"),
            ("nvei", "Assurance mobilité NVEI"),
            ("camping-car", "Assurance camping-car"),
            ("camping-cars", "Assurance camping-car"),
            ("assurance santé", "Assurance santé à prix avantageux"),
            ("protection juridique", "Protection juridique"),
            ("regroupement de crédit", "Regroupement de crédits"),
            ("cashback", "Programme cashback"),
            ("cagnotte", "Cagnotte fidélité"),
            ("voyager moins cher", "Voyage à prix réduit"),
            ("e-carte bleue", "Service e-Carte Bleue"),
            ("prêt immobilier", "Prêt immobilier"),
            ("assurance auto", "Assurance auto"),
            ("prêt personnel", "Prêt personnel"),
            ("assurance habitation", "Assurance habitation"),
            ("responsabilité civile", "Responsabilité civile"),
            ("credit", "Financement simplifié"),
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
    def _extract_promotional_topic(cls, source_preview: str) -> str | None:
        cleaned_preview = re.sub(r"\s+", " ", source_preview).strip()
        cleaned_preview = re.sub(
            r"(?i)accès à vos comptes par l'écran de connexion pleine page|accéder au menu principal|accéder au contenu éditorial|accéder au pied de page|accéder aux autres espaces|devenir client|mon espace|nous contacter|découvrez nos métiers|metiers|banque privée|particulier|professionnel|entreprise|etudiant|journaliste",
            " ",
            cleaned_preview,
        )
        candidates = [
            candidate.strip(" :-")
            for candidate in re.split(r"[.!?\n]+", cleaned_preview)
            if candidate.strip()
        ]
        best_phrase: str | None = None
        best_score = -10_000
        for candidate in candidates:
            candidate = cls._clean_topic_candidate(candidate)
            if len(candidate) < 18:
                continue
            lowered_candidate = candidate.lower()
            if cls._is_noisy_topic_candidate(lowered_candidate):
                continue
            score = sum(
                keyword in lowered_candidate
                for keyword in cls.PROMOTIONAL_TOPIC_KEYWORDS
            )
            if any(
                lowered_candidate.startswith(prefix)
                for prefix in cls.BAD_TOPIC_PREFIXES
            ):
                score -= 5
            if any(
                substring in lowered_candidate for substring in cls.BAD_TOPIC_SUBSTRINGS
            ):
                score -= 5
            words = candidate.split()
            phrase = " ".join(words[:7]).strip(" ,;:-")
            if len(phrase) < 12:
                continue
            if cls._is_noisy_topic_candidate(phrase.lower()):
                continue
            if score > best_score:
                best_score = score
                best_phrase = phrase[0].upper() + phrase[1:]
        if best_phrase is None or best_score < 1:
            return None
        return best_phrase

    @classmethod
    def _infer_legitimate_focus(cls, source_preview: str) -> str:
        lowered = source_preview.lower()
        focus_map = (
            (
                (
                    "mondial relay",
                    "colis",
                    "livraison",
                    "point relais",
                    "chronopost",
                    "coursier",
                    "livreur",
                ),
                "vos notifications de livraison",
            ),
            (
                ("emploi", "cv", "recrutement", "temps partiel"),
                "vos offres d'emploi reçues",
            ),
            (
                ("loterie", "gain", "gagnants", "euro-millions"),
                "les promesses de gain",
            ),
            (
                ("location", "locataire", "location saisonnière"),
                "les demandes de location",
            ),
            (
                (
                    "notification",
                    "notifications",
                    "virement",
                    "sms",
                    "apple pay",
                    "samsung pay",
                    "messagerie sécurisée",
                    "e-carte bleue",
                ),
                "vos paiements et notifications",
            ),
            (("réseaux sociaux", "internet"), "vos échanges sur Internet"),
            (
                ("fraude", "opération frauduleuse"),
                "la prévention des opérations frauduleuses",
            ),
            (
                ("arnaque", "escroquerie", "signalement"),
                "les messages suspects",
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

    @classmethod
    def _infer_awareness_focus(cls, source_preview: str) -> str:
        lowered = source_preview.lower()
        focus_map = (
            (
                (
                    "mondial relay",
                    "colis",
                    "livraison",
                    "point relais",
                    "chronopost",
                    "coursier",
                    "livreur",
                ),
                "les faux messages de livraison",
            ),
            (
                ("emploi", "cv", "recrutement", "temps partiel"),
                "les faux messages d'emploi",
            ),
            (
                ("loterie", "gain", "gagnants", "euro-millions"),
                "les faux gains et loteries",
            ),
            (
                ("location", "locataire", "location saisonnière"),
                "les demandes de location suspectes",
            ),
            (
                ("appel frauduleux", "appel suspect", "téléphone"),
                "les appels frauduleux",
            ),
            (
                ("données bancaires", "carte bancaire"),
                "la protection de vos données bancaires",
            ),
            (
                ("réseaux sociaux", "internet"),
                "les fraudes sur Internet et les réseaux sociaux",
            ),
            (("arnaque", "escroquerie", "signalement"), "les messages suspects"),
            (("mail", "e-mail", "sms"), "les messages suspects"),
            (("fraude", "opération frauduleuse"), "les opérations frauduleuses"),
        )
        for markers, focus in focus_map:
            if any(marker in lowered for marker in markers):
                return focus
        return "les messages suspects"

    @classmethod
    def _extract_legitimate_topic(cls, source_preview: str, *, fallback: str) -> str:
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
        best_phrase: str | None = None
        best_score = -10_000
        for candidate in candidates:
            candidate = re.sub(r"^\d+\s*[-:]\s*", "", candidate).strip()
            if len(candidate) < 18:
                continue
            lowered_candidate = candidate.lower()
            if cls._is_noisy_topic_candidate(lowered_candidate):
                continue
            score = sum(
                keyword in lowered_candidate
                for keyword in cls.LEGITIMATE_TOPIC_KEYWORDS
            )
            if any(
                lowered_candidate.startswith(prefix)
                for prefix in cls.BAD_TOPIC_PREFIXES
            ):
                score -= 5
            if any(
                substring in lowered_candidate for substring in cls.BAD_TOPIC_SUBSTRINGS
            ):
                score -= 5
            words = candidate.split()
            phrase = " ".join(words[:7]).strip(" ,;:-")
            if len(phrase) < 12:
                continue
            if cls._is_noisy_topic_candidate(phrase.lower()):
                continue
            if score > best_score:
                best_score = score
                best_phrase = phrase[0].upper() + phrase[1:]
        if best_phrase is None or best_score < 1:
            return fallback
        if cls._count_page_like_subject_hits(best_phrase) > 0:
            return fallback
        return best_phrase

    @classmethod
    def _extract_topic_phrase(cls, source_preview: str, *, fallback: str) -> str:
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
            candidate = cls._clean_topic_candidate(candidate)
            if len(candidate) < 18:
                continue
            if cls._is_noisy_topic_candidate(candidate.lower()):
                continue
            words = candidate.split()
            phrase = " ".join(words[:6]).strip(" ,;:-")
            if len(phrase) >= 12 and not cls._is_noisy_topic_candidate(phrase.lower()):
                return phrase[0].upper() + phrase[1:]
        return fallback

    @staticmethod
    def _clean_topic_candidate(candidate: str) -> str:
        cleaned_candidate = re.sub(r"^\d+\s*[-:]\s*", "", candidate).strip()
        cleaned_candidate = re.sub(
            r"(?i)^(article|offres? et services|la banque postale|lcl banque privée|lcl banque et|lcl wealth management)\s+",
            "",
            cleaned_candidate,
        )
        cleaned_candidate = re.split(
            r"(?i)\s+(?:accéder|découvrez|vous|avec|pour|comment|quelles?|quel(?:le|s)?|retrouvez|simplement|afin de)\b",
            cleaned_candidate,
            maxsplit=1,
        )[0].strip()
        cleaned_candidate = re.sub(
            r"(?i)\b(?:de la banque postale|chez lcl|chez la banque postale)\b",
            "",
            cleaned_candidate,
        )
        return cleaned_candidate.strip(" ,;:-")

    @classmethod
    def _is_noisy_topic_candidate(cls, text: str) -> bool:
        lowered = text.lower().strip()
        if any(marker in lowered for marker in cls.NOISY_TOPIC_MARKERS):
            return True
        if any(marker in lowered for marker in cls.BAD_TOPIC_SUBSTRINGS):
            return True
        if "[phone]" in lowered or "[email]" in lowered or "[url]" in lowered:
            return True
        if re.search(r"\b\d+\s*commentaires?\b", lowered):
            return True
        if re.search(r"\b(?:up vote|down vote)\b", lowered):
            return True
        if re.search(r"\b(?:le|la)\s+\d{2}/\d{2}/\d{4}\b", lowered):
            return True
        if re.match(
            (
                r"^(?:je|j'|moi|mon|ma|mes|nous|notre|guy\s+le|ps\s*:|bref\b|ce qui m'a|"
                r"bonjour\b|choisissez\b|pensez\b|sur mon compte\b|ils ont\b|en cas de besoin\b|"
                r"votre engagement massif\b|\"\s*j'ai\b)"
            ),
            lowered,
        ):
            return True
        return False

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
        subject_page_like_hits = cls._count_page_like_subject_hits(subject)
        preview_page_like_hits = cls._count_page_like_subject_hits(source_preview)
        if target_label == "legitimate" and (
            subject_page_like_hits > 0
            or (
                preview_page_like_hits > 0
                and cls._has_generic_legitimate_subject(subject)
            )
        ):
            review_notes.append("page_like_legitimate_subject")

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
            "subject_page_like_hits": subject_page_like_hits,
            "preview_page_like_hits": preview_page_like_hits,
        }
        return review_state, review_notes, quality_signals

    @classmethod
    def _count_page_like_subject_hits(cls, subject: str) -> int:
        lowered = subject.lower()
        return sum(marker in lowered for marker in cls.PAGE_LIKE_SUBJECT_MARKERS)

    @classmethod
    def _has_generic_legitimate_subject(cls, subject: str) -> bool:
        lowered = subject.lower()
        return any(
            lowered.startswith(prefix)
            for prefix in cls.GENERIC_LEGITIMATE_SUBJECT_PREFIXES
        )

    @classmethod
    def _describe_risk_channels(cls, source_preview: str) -> str:
        lowered = source_preview.lower()
        channels: list[str] = []
        if any(marker in lowered for marker in ("e-mail", "mail")):
            channels.append("par e-mail")
        if "sms" in lowered:
            channels.append("par SMS")
        if any(marker in lowered for marker in ("appel", "téléphone")):
            channels.append("par téléphone")
        if "réseaux sociaux" in lowered:
            channels.append("sur les réseaux sociaux")
        if not channels:
            return "par message ou téléphone"
        if len(channels) == 1:
            return channels[0]
        return ", ".join(channels[:-1]) + f" ou {channels[-1]}"

    @classmethod
    def _extract_warning_action(cls, source_preview: str) -> str:
        lowered = source_preview.lower()
        if any(marker in lowered for marker in ("données bancaires", "carte bancaire")):
            return "Ne communiquez jamais vos données bancaires, vos codes de validation ou les informations de votre carte à la suite d'un contact inattendu."
        if any(
            marker in lowered
            for marker in ("appel frauduleux", "appel suspect", "téléphone")
        ):
            return "Ne rappelez jamais un numéro communiqué dans un appel ou un message suspect et ne validez aucune opération sans contrôle préalable."
        if any(marker in lowered for marker in ("réseaux sociaux", "internet")):
            return "Évitez de cliquer sur un lien reçu de manière inattendue et vérifiez toujours la demande depuis votre espace ou vos canaux habituels."
        return "Ne répondez jamais à une demande sensible sans avoir vérifié l'origine du contact et la légitimité de la procédure."

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
