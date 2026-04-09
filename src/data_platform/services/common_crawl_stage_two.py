from __future__ import annotations

import re
from typing import Any

from data_platform.services.stage_two_models import StageTwoReviewResult


class CommonCrawlStageTwoService:
    NAV_MARKERS = (
        "accès à vos comptes par l'écran de connexion pleine page",
        "accéder au menu principal",
        "accéder au contenu éditorial",
        "accéder au pied de page",
        "accéder aux autres espaces",
        "devenir client",
        "mon espace",
        "partagez",
        "imprimer",
        "lecture ",
    )
    PAGE_MARKERS = (
        "article ",
        "interview ",
        "thématiques",
        "solutions associées",
        "articles associés",
        "consulter",
        "en savoir plus",
        "service gratuit + prix d'un appel",
        "recherche bureau de poste",
    )
    EMAIL_LIKE_MARKERS = (
        "bonjour",
        "bonsoir",
        "cher client",
        "chère cliente",
        "cher(e)",
        "cliquez",
        "votre compte",
        "cordialement",
        "merci de",
        "nous avons",
        "confirmez",
        "mise à jour",
        "mot de passe",
        "connexion",
    )
    TRANSACTION_MARKERS = (
        "vous recevrez",
        "mot de passe provisoire",
        "code à usage unique",
        "certicode",
        "courrier",
        "sms",
        "e-mail",
        "email",
        "espace client",
        "opération frauduleuse",
        "virement par sms",
        "virements par sms",
        "virement instantané",
    )
    SECURITY_MARKERS = (
        "mot de passe",
        "réinitialiser",
        "sécuriser",
        "sécurité",
        "code à usage unique",
        "certicode",
        "opération frauduleuse",
        "espace client",
    )
    GUIDANCE_MARKERS = (
        "comment me protéger",
        "comment sécuriser",
        "découvrez comment",
        "ce service vous permet",
        "nous vous aidons",
        "nous vous invitons",
        "en cas de difficulté",
        "contactez votre service client",
        "votre service client",
        "retrouvez",
        "consultez",
    )
    PRODUCT_MARKERS = (
        "1€/mois",
        "1 eur/mois",
        "formule de compte",
        "découvrir la formule",
        "cagnotte",
        "cashback",
        "verser à un proche",
        "offre",
        "tarif",
        "assurance habitation",
        "banque au service de tous",
    )
    HARD_ACCEPT_MARKERS = (
        "vous recevrez",
        "vous est envoyé",
        "veuillez renseigner",
        "mot de passe provisoire",
        "code à usage unique",
        "nous vous invitons",
        "par e-mail",
        "par sms",
        "adresse email personnelle",
        "numéro de téléphone mobile",
    )
    DELIVERY_MARKERS = (
        "vous recevrez",
        "vous est envoyé",
        "par e-mail",
        "par sms",
        "par courrier",
        "adresse email personnelle",
        "numéro de téléphone mobile",
        "messagerie personnelle",
        "messagerie sécurisée",
        "nous vous sollicite",
    )
    NOTIFICATION_MARKERS = (
        "vous est envoyé",
        "vous recevrez",
        "mot de passe provisoire",
        "vous êtes informé de la mise en ligne",
        "alerte sms",
        "alertes sms",
        "notification vous sera adressé",
        "notification vous sera adressée",
        "a été envoyé dans ma messagerie sécurisée",
        "notification paramétrable",
        "notifications paramétrables",
        "notification push",
        "notifications push",
    )
    EXCLUDE_MARKERS = (
        "serious game",
        "apprenez à les déjouer",
        "article ",
        "interview ",
        "lecture ",
        "thématiques",
        "articles associés",
        "découvrir",
    )
    AWARENESS_MARKERS = (
        "voici quelques conseils",
        "ne communiquez jamais",
        "savez-vous comment",
        "protéger des risques",
        "escroqueries par e-mail et sms",
        "avez-vous déjà été exposé",
    )
    PROMOTIONAL_MARKERS = (
        "offre",
        "promotion",
        "réduction",
        "remise",
        "code promo",
        "livraison offerte",
        "profitez",
        "newsletter",
        "bons plans",
        "vente privée",
    )
    ACCOUNT_RECOVERY_MARKERS = (
        "messagerie sécurisée",
        "adresse email personnelle",
        "numéro de téléphone mobile",
        "service client",
        "espace client",
        "conseiller",
        "mot de passe provisoire",
        "code à usage unique",
        "notification",
        "alertes sms",
        "notification push",
    )
    PHISHING_REPORT_MARKERS = (
        "site internet frauduleux",
        "page miroir",
        "message reçu ce jour",
        "message recu ce jour",
        "sms reçu",
        "sms recu",
        "faux colis",
        "potentiel phishing",
        "phishing de données",
        "données personnelles et bancaires",
        "arnaque téléphonique",
        "arnaque telephonique",
        "arnaque sms",
        "lien frauduleux",
        "escroquerie au faux colis",
        "soyez vigilant",
    )
    PHISHING_LURE_MARKERS = (
        "mondial relay",
        "coursier",
        "livreur",
        "livraison",
        "colis",
        "suspension",
        "confirmez votre compte",
        "vérifier votre compte",
        "sans délai",
        "lien sécurisé",
        "réattrib",
        "je reçois un message",
        "je recois un message",
        "dirige vers un site internet",
        "récupérer un colis",
        "recuperer un colis",
    )
    PHISHING_QUERY_HINTS = (
        "signal-arnaques",
        "scam_reports_fr",
        "signal-spam",
        "signal_spam_fr",
        "openphish",
        "phishing_feed",
    )
    PHISHING_AWARENESS_MARKERS = (
        "assistance aux victimes de cybermalveillance",
        "sensibiliser au risque cyber",
        "menaces numériques",
        "menaces numeriques",
        "moyens de s'en protéger",
        "moyens de s'en proteger",
        "alerte cyber",
        "campagne de messages d'escroquerie",
        "campagne de messages d’escroquerie",
        "campagne de phishing",
        "campagne de hameçonnage",
        "campagne de hameconnage",
        "signaler un spam",
        "signalez les spams",
        "pages de phishing bloquées",
        "pages de phishing bloquees",
    )
    PHISHING_AWARENESS_EXCLUDE_MARKERS = (
        "événements passés",
        "evenements passes",
        "journée européenne",
        "journee europeenne",
        "expoprotection",
        "paris games week",
        "viva technology",
        "baromètre",
        "barometre",
        "trimestre",
        "téléchargez le baromètre",
        "telechargez le barometre",
    )
    PHISHING_AWARENESS_QUERY_HINTS = (
        "cert_gov_fr",
        "reporting_gov_fr",
        "signal_spam_fr",
        "cybermalveillance.gouv.fr",
        "internet-signalement.gouv.fr",
        "signal-spam.fr",
    )

    @classmethod
    def review(
        cls,
        cleaned_text: str,
        raw_content: dict[str, Any],
    ) -> StageTwoReviewResult:
        extracted_text, extraction_trace = cls._extract_window(cleaned_text)
        route_outcome, route_reason, route_subtype, route_trace, evidence = (
            cls._route_candidate(extracted_text, raw_content, extraction_trace)
        )
        derived_payload = {
            "derived_type": "common_crawl_stage_two_candidate",
            "candidate_subtype": route_subtype,
            "promotion_eligible": route_outcome == "accepted",
            "source_category": raw_content.get("category"),
            "source_query": raw_content.get("query"),
            "source_query_label": raw_content.get("query_label"),
            "source_url": raw_content.get("url"),
            "phishing_relevance": route_subtype == "phishing_lure_candidate",
            "marker_evidence": evidence,
        }
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
        prepared = text
        for marker in (
            CommonCrawlStageTwoService.NAV_MARKERS
            + CommonCrawlStageTwoService.PAGE_MARKERS
        ):
            prepared = re.sub(
                re.escape(marker),
                f"\n{marker}\n",
                prepared,
                flags=re.IGNORECASE,
            )
        segments = [
            segment.strip()
            for segment in re.split(r"(?<=[.!?])\s+|\n+", prepared)
            if segment.strip()
        ]
        return [segment for segment in segments if len(segment) >= 30]

    @staticmethod
    def _strip_known_phrases(text: str, markers: tuple[str, ...]) -> str:
        cleaned_text = text
        for marker in markers:
            cleaned_text = re.sub(
                re.escape(marker),
                " ",
                cleaned_text,
                flags=re.IGNORECASE,
            )
        return re.sub(r"\s+", " ", cleaned_text).strip()

    @classmethod
    def _extract_window(cls, text: str) -> tuple[str, tuple[str, ...]]:
        trace_steps = ["common_crawl_window_search_started"]
        segments = cls._split_candidate_segments(text)
        if not segments:
            trace_steps.append("common_crawl_no_segments_found")
            return text, tuple(trace_steps)

        best_score = 0
        best_window: str | None = None
        for start in range(len(segments)):
            for size in range(1, 5):
                end = start + size
                if end > len(segments):
                    break
                candidate_window = " ".join(segments[start:end]).strip()
                transaction_hits = cls._count_markers(
                    candidate_window,
                    cls.TRANSACTION_MARKERS,
                )
                delivery_hits = cls._count_markers(
                    candidate_window,
                    cls.DELIVERY_MARKERS,
                )
                notification_hits = cls._count_markers(
                    candidate_window,
                    cls.NOTIFICATION_MARKERS,
                )
                security_hits = cls._count_markers(
                    candidate_window,
                    cls.SECURITY_MARKERS,
                )
                email_hits = cls._count_markers(
                    candidate_window,
                    cls.EMAIL_LIKE_MARKERS,
                )
                guidance_hits = cls._count_markers(
                    candidate_window,
                    cls.GUIDANCE_MARKERS,
                )
                product_hits = cls._count_markers(
                    candidate_window,
                    cls.PRODUCT_MARKERS,
                )
                exclude_hits = cls._count_markers(candidate_window, cls.EXCLUDE_MARKERS)
                score = transaction_hits * 4
                score += delivery_hits * 4
                score += notification_hits * 4
                score += security_hits * 3
                score += email_hits * 2
                score -= guidance_hits * 2
                score -= product_hits * 3
                score -= exclude_hits * 3
                if score > best_score:
                    best_score = score
                    best_window = candidate_window

        if best_window is None or best_score < 7:
            trace_steps.append("common_crawl_no_message_window_found")
            return text, tuple(trace_steps)

        candidate_window = cls._strip_known_phrases(
            best_window,
            cls.NAV_MARKERS + cls.PAGE_MARKERS,
        )
        if cls._count_markers(candidate_window, cls.EXCLUDE_MARKERS) >= 2:
            trace_steps.append("common_crawl_window_rejected_by_page_markers")
            return text, tuple(trace_steps)
        if (
            cls._count_markers(candidate_window, cls.TRANSACTION_MARKERS)
            + cls._count_markers(candidate_window, cls.DELIVERY_MARKERS)
            + cls._count_markers(candidate_window, cls.SECURITY_MARKERS)
            + cls._count_markers(candidate_window, cls.NOTIFICATION_MARKERS)
        ) < 3:
            trace_steps.append("common_crawl_window_too_weak")
            return text, tuple(trace_steps)

        trace_steps.append("common_crawl_transactional_window_extracted")
        return candidate_window, tuple(trace_steps)

    @classmethod
    def _route_candidate(
        cls,
        text: str,
        raw_content: dict[str, Any],
        extraction_trace: tuple[str, ...],
    ) -> tuple[str, str | None, str, tuple[str, ...], dict[str, int | str | None]]:
        trace_steps = ["common_crawl_cleaned"]
        lowered_text = text.lower()
        nav_hits = cls._count_markers(text, cls.NAV_MARKERS)
        page_hits = cls._count_markers(text, cls.PAGE_MARKERS)
        email_hits = cls._count_markers(text, cls.EMAIL_LIKE_MARKERS)
        transaction_hits = cls._count_markers(text, cls.TRANSACTION_MARKERS)
        security_hits = cls._count_markers(text, cls.SECURITY_MARKERS)
        guidance_hits = cls._count_markers(text, cls.GUIDANCE_MARKERS)
        product_hits = cls._count_markers(text, cls.PRODUCT_MARKERS)
        promo_hits = cls._count_markers(text, cls.PROMOTIONAL_MARKERS)
        hard_accept_hits = cls._count_markers(text, cls.HARD_ACCEPT_MARKERS)
        delivery_hits = cls._count_markers(text, cls.DELIVERY_MARKERS)
        notification_hits = cls._count_markers(text, cls.NOTIFICATION_MARKERS)
        awareness_hits = cls._count_markers(text, cls.AWARENESS_MARKERS)
        account_recovery_hits = cls._count_markers(text, cls.ACCOUNT_RECOVERY_MARKERS)
        phishing_report_hits = cls._count_markers(text, cls.PHISHING_REPORT_MARKERS)
        phishing_lure_hits = cls._count_markers(text, cls.PHISHING_LURE_MARKERS)
        phishing_awareness_hits = cls._count_markers(
            text, cls.PHISHING_AWARENESS_MARKERS
        )
        phishing_awareness_exclude_hits = cls._count_markers(
            text, cls.PHISHING_AWARENESS_EXCLUDE_MARKERS
        )
        raw_category = str(raw_content.get("category", "")).lower()
        raw_label = str(raw_content.get("label") or "").lower()
        raw_query = str(raw_content.get("query") or "").lower()
        raw_url = str(raw_content.get("url") or "").lower()
        raw_query_label = str(
            raw_content.get("query_label") or raw_label or raw_query or ""
        ).lower()
        phishing_query_hint = any(
            hint in raw_query_label or hint in raw_query or hint in raw_url
            for hint in cls.PHISHING_QUERY_HINTS
        )
        phishing_awareness_query_hint = any(
            hint in raw_query_label or hint in raw_query or hint in raw_url
            for hint in cls.PHISHING_AWARENESS_QUERY_HINTS
        )

        evidence = {
            "nav_hits": nav_hits,
            "page_hits": page_hits,
            "email_hits": email_hits,
            "transaction_hits": transaction_hits,
            "security_hits": security_hits,
            "guidance_hits": guidance_hits,
            "product_hits": product_hits,
            "promo_hits": promo_hits,
            "delivery_hits": delivery_hits,
            "notification_hits": notification_hits,
            "awareness_hits": awareness_hits,
            "account_recovery_hits": account_recovery_hits,
            "phishing_report_hits": phishing_report_hits,
            "phishing_lure_hits": phishing_lure_hits,
            "phishing_awareness_hits": phishing_awareness_hits,
            "phishing_awareness_exclude_hits": phishing_awareness_exclude_hits,
            "raw_category": raw_category or None,
            "raw_query_label": raw_query_label or None,
        }

        trace_steps.extend(
            step
            for condition, step in (
                (bool(nav_hits), "common_crawl_navigation_markers_detected"),
                (bool(page_hits), "common_crawl_page_markers_detected"),
                (bool(email_hits), "common_crawl_email_markers_detected"),
                (bool(awareness_hits), "common_crawl_awareness_markers_detected"),
                (
                    bool(phishing_report_hits),
                    "common_crawl_phishing_report_markers_detected",
                ),
            )
            if condition
        )

        if (raw_category == "phishing_related" or phishing_query_hint) and (
            phishing_report_hits >= 2
            or (phishing_report_hits >= 1 and phishing_lure_hits >= 2)
            or (
                phishing_report_hits >= 1
                and any(
                    marker in lowered_text
                    for marker in ("confirmez", "vérification", "sans délai", "cliquez")
                )
            )
        ):
            trace_steps.extend(
                [
                    "common_crawl_phishing_lure_markers_detected",
                    "common_crawl_route_to_specialized_extractor",
                ]
            )
            return (
                "specialized_processing",
                "common_crawl_phishing_lure_candidate",
                "phishing_lure_candidate",
                tuple(trace_steps),
                evidence,
            )

        if (
            raw_category == "phishing_related"
            and phishing_awareness_query_hint
            and phishing_awareness_hits >= 1
            and phishing_awareness_exclude_hits == 0
        ):
            trace_steps.extend(
                [
                    "common_crawl_phishing_awareness_markers_detected",
                    "common_crawl_route_to_specialized_extractor",
                ]
            )
            return (
                "specialized_processing",
                "common_crawl_phishing_awareness_content",
                "awareness_or_report",
                tuple(trace_steps),
                evidence,
            )

        if awareness_hits:
            trace_steps.append("common_crawl_route_to_specialized_extractor")
            return (
                "specialized_processing",
                "common_crawl_awareness_content",
                "awareness_or_report",
                tuple(trace_steps),
                evidence,
            )

        if (
            hard_accept_hits >= 1
            and delivery_hits >= 1
            and notification_hits >= 1
            and transaction_hits >= 2
            and security_hits >= 1
            and guidance_hits <= 2
            and product_hits == 0
            and nav_hits <= 1
            and page_hits <= 1
        ):
            trace_steps.append("common_crawl_direct_message_gate_passed")
            return (
                "accepted",
                None,
                "transactional_legitimate",
                tuple(trace_steps),
                evidence,
            )

        if (
            promo_hits >= 2
            or raw_category == "spam_like"
            or "newsletter" in raw_query_label
        ):
            trace_steps.extend(
                [
                    "common_crawl_promotional_markers_detected",
                    "common_crawl_route_to_specialized_extractor",
                ]
            )
            return (
                "specialized_processing",
                "common_crawl_promotional_candidate",
                "promotional_spam",
                tuple(trace_steps),
                evidence,
            )

        if (
            any(
                step in extraction_trace
                for step in (
                    "common_crawl_no_message_window_found",
                    "common_crawl_window_too_weak",
                )
            )
            and raw_category == "legitimate"
            and product_hits == 0
            and account_recovery_hits >= 3
            and (delivery_hits + notification_hits + security_hits) >= 1
            and nav_hits <= 2
            and page_hits <= 1
        ):
            trace_steps.extend(
                [
                    "common_crawl_account_recovery_markers_detected",
                    "common_crawl_route_to_specialized_extractor",
                ]
            )
            return (
                "specialized_processing",
                "common_crawl_account_recovery_candidate",
                "instructional_legitimate",
                tuple(trace_steps),
                evidence,
            )

        if (
            (
                transaction_hits >= 2
                or (transaction_hits + delivery_hits + notification_hits) >= 3
            )
            and (
                email_hits >= 1
                or delivery_hits >= 1
                or security_hits >= 1
                or notification_hits >= 1
            )
            and page_hits <= 2
        ):
            trace_steps.extend(
                [
                    "common_crawl_instructional_markers_detected",
                    "common_crawl_route_to_specialized_extractor",
                ]
            )
            return (
                "specialized_processing",
                "common_crawl_instructional_candidate",
                "instructional_legitimate",
                tuple(trace_steps),
                evidence,
            )

        if (
            any(
                step in extraction_trace
                for step in (
                    "common_crawl_no_message_window_found",
                    "common_crawl_window_too_weak",
                )
            )
            and raw_category == "legitimate"
            and nav_hits <= 1
            and page_hits == 0
            and guidance_hits <= 1
            and (transaction_hits + delivery_hits + notification_hits + security_hits)
            >= 3
        ):
            trace_steps.extend(
                [
                    "common_crawl_weak_window_recovered",
                    "common_crawl_route_to_specialized_extractor",
                ]
            )
            return (
                "specialized_processing",
                "common_crawl_weak_window_candidate",
                "instructional_legitimate",
                tuple(trace_steps),
                evidence,
            )

        if (
            raw_category == "legitimate"
            and product_hits >= 1
            and (promo_hits >= 1 or nav_hits >= 2)
            and page_hits <= 1
            and transaction_hits == 0
            and delivery_hits == 0
            and security_hits == 0
        ):
            trace_steps.extend(
                [
                    "common_crawl_product_offer_recovered",
                    "common_crawl_route_to_specialized_extractor",
                ]
            )
            return (
                "specialized_processing",
                "common_crawl_product_offer_candidate",
                "promotional_spam",
                tuple(trace_steps),
                evidence,
            )

        if nav_hits >= 2 and transaction_hits < 2:
            trace_steps.append("common_crawl_navigation_heavy_holdout")
            return (
                "specialized_processing",
                "common_crawl_navigation_heavy_holdout",
                "navigation_heavy_holdout",
                tuple(trace_steps),
                evidence,
            )

        if any(
            step in extraction_trace
            for step in (
                "common_crawl_no_segments_found",
                "common_crawl_no_message_window_found",
                "common_crawl_window_rejected_by_page_markers",
                "common_crawl_window_too_weak",
            )
        ):
            trace_steps.append("common_crawl_no_window_holdout")
            return (
                "specialized_processing",
                "common_crawl_no_window_holdout",
                "no_window_holdout",
                tuple(trace_steps),
                evidence,
            )

        trace_steps.append("common_crawl_route_to_specialized_extractor")
        return (
            "specialized_processing",
            "common_crawl_requires_chunk_extraction",
            "instructional_legitimate",
            tuple(trace_steps),
            evidence,
        )
