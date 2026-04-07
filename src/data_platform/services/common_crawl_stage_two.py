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
        "veuillez",
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
        "veuillez",
        "nous vous aidons",
        "nous vous invitons",
        "en cas de difficulté",
        "contactant votre service client",
        "rendez-vous dans votre bureau de poste",
        "mot de passe provisoire",
        "code à usage unique",
        "certicode",
        "courrier",
        "sms",
        "e-mail",
        "email",
        "espace client",
        "opération frauduleuse",
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
        "notification vous sera adressé",
        "notification vous sera adressée",
        "a été envoyé dans ma messagerie sécurisée",
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
        segments = [
            segment.strip()
            for segment in re.split(r"(?<=[.!?])\s+|\n+", text)
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
        best_index = -1
        for index, segment in enumerate(segments):
            transaction_hits = cls._count_markers(segment, cls.TRANSACTION_MARKERS)
            email_hits = cls._count_markers(segment, cls.EMAIL_LIKE_MARKERS)
            exclude_hits = cls._count_markers(segment, cls.EXCLUDE_MARKERS)
            score = transaction_hits * 3 + email_hits * 2 - exclude_hits * 3
            if score > best_score:
                best_score = score
                best_index = index

        if best_index == -1 or best_score < 4:
            trace_steps.append("common_crawl_no_message_window_found")
            return text, tuple(trace_steps)

        start = max(0, best_index - 1)
        end = min(len(segments), best_index + 3)
        candidate_window = " ".join(segments[start:end]).strip()
        candidate_window = cls._strip_known_phrases(
            candidate_window,
            cls.NAV_MARKERS + cls.PAGE_MARKERS,
        )
        if cls._count_markers(candidate_window, cls.EXCLUDE_MARKERS) >= 2:
            trace_steps.append("common_crawl_window_rejected_by_page_markers")
            return text, tuple(trace_steps)
        if cls._count_markers(candidate_window, cls.TRANSACTION_MARKERS) < 2:
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
        nav_hits = cls._count_markers(text, cls.NAV_MARKERS)
        page_hits = cls._count_markers(text, cls.PAGE_MARKERS)
        email_hits = cls._count_markers(text, cls.EMAIL_LIKE_MARKERS)
        transaction_hits = cls._count_markers(text, cls.TRANSACTION_MARKERS)
        promo_hits = cls._count_markers(text, cls.PROMOTIONAL_MARKERS)
        hard_accept_hits = cls._count_markers(text, cls.HARD_ACCEPT_MARKERS)
        delivery_hits = cls._count_markers(text, cls.DELIVERY_MARKERS)
        notification_hits = cls._count_markers(text, cls.NOTIFICATION_MARKERS)
        awareness_hits = cls._count_markers(text, cls.AWARENESS_MARKERS)
        raw_category = str(raw_content.get("category", "")).lower()
        raw_query_label = str(
            raw_content.get("query_label") or raw_content.get("query") or ""
        ).lower()

        evidence = {
            "nav_hits": nav_hits,
            "page_hits": page_hits,
            "email_hits": email_hits,
            "transaction_hits": transaction_hits,
            "promo_hits": promo_hits,
            "delivery_hits": delivery_hits,
            "notification_hits": notification_hits,
            "awareness_hits": awareness_hits,
            "raw_category": raw_category or None,
        }

        trace_steps.extend(
            step
            for condition, step in (
                (bool(nav_hits), "common_crawl_navigation_markers_detected"),
                (bool(page_hits), "common_crawl_page_markers_detected"),
                (bool(email_hits), "common_crawl_email_markers_detected"),
                (bool(awareness_hits), "common_crawl_awareness_markers_detected"),
            )
            if condition
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

        if transaction_hits >= 2 and email_hits >= 1 and page_hits <= 1:
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
