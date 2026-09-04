from __future__ import annotations

import html
import re
from collections.abc import Iterable

from bs4 import BeautifulSoup


class CommonCrawlContentService:
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
    MESSAGE_MARKERS = (
        "vous recevrez",
        "vous est envoyé",
        "par sms",
        "par e-mail",
        "par courrier",
        "messagerie sécurisée",
        "mot de passe provisoire",
        "code à usage unique",
        "certicode",
        "opération frauduleuse",
        "espace client",
        "adresse email personnelle",
        "numéro de téléphone mobile",
        "notification",
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
    NOISE_MARKERS = (
        "accepter les cookies",
        "tous droits réservés",
        "all rights reserved",
        "contactez-nous",
        "plan du site",
        "gestion des cookies",
    )
    LEGITIMATE_URL_POSITIVE_MARKERS = (
        "mot-de-passe",
        "mot_de_passe",
        "reinitial",
        "secur",
        "fraude",
        "alerte",
        "notification",
        "releve",
        "sms",
        "email",
        "messagerie",
        "espace-client",
        "virement",
        "paiement",
        "code",
        "document",
    )
    LEGITIMATE_URL_NEGATIVE_MARKERS = (
        "/article",
        "/actualite",
        "/actualites",
        "/interview",
        "/magazine",
        "/blog",
        "/presse",
        "/news",
        "/solutions",
        "/metiers",
        "/groupe",
        "/a-propos",
    )
    SPAM_URL_POSITIVE_MARKERS = (
        "newsletter",
        "promo",
        "promotion",
        "offre",
        "reduction",
        "soldes",
        "bon-plan",
        "vente-privee",
    )
    PHISHING_URL_POSITIVE_MARKERS = (
        "phishing",
        "arnaque",
        "fraude",
        "escroquerie",
        "scam",
        "signalement",
        "signal-spam",
    )
    BLOCK_TAGS = (
        "main",
        "article",
        "section",
        "div",
        "p",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
    )
    MIN_SEGMENT_LEN = 24

    @classmethod
    def extract_text_from_html(cls, html_text: str, max_length: int = 10_000) -> str:
        soup = BeautifulSoup(html_text, "html.parser")
        for tag in soup.find_all(
            ["script", "style", "meta", "link", "noscript", "iframe", "svg"]
        ):
            tag.decompose()
        for tag in soup.find_all(["nav", "header", "footer", "aside", "form"]):
            tag.decompose()

        blocks: list[str] = []
        seen_blocks: set[str] = set()
        for element in soup.find_all(cls.BLOCK_TAGS):
            block = cls._normalize_text(element.get_text("\n", strip=True))
            if len(block) < cls.MIN_SEGMENT_LEN or block in seen_blocks:
                continue
            seen_blocks.add(block)
            blocks.append(block)

        if blocks:
            scored_blocks = sorted(blocks, key=cls.score_text_window, reverse=True)
            candidate = "\n".join(
                block
                for block in scored_blocks[:8]
                if cls.score_text_window(block) >= 0
            ) or "\n".join(scored_blocks[:5])
        else:
            candidate = cls._normalize_text(soup.get_text("\n", strip=True))

        return cls.clean_web_text(candidate, max_length=max_length)

    @classmethod
    def clean_web_text(cls, text: str, max_length: int = 2500) -> str:
        normalized = cls._normalize_text(text)
        if not normalized:
            return ""

        segments = cls._split_segments(normalized)
        if candidate := cls._extract_best_window(segments):
            normalized = cls._strip_known_noise(candidate)
        else:
            normalized = cls._strip_soft_noise(normalized)

        normalized = cls._normalize_text(normalized)
        if len(normalized) > max_length:
            normalized = f"{normalized[:max_length]}... [TRUNCATED_WEB]"
        return normalized

    @classmethod
    def score_url(cls, url: str, category: str) -> int:
        lowered_url = url.lower()
        if category == "legitimate":
            positive_hits = cls._count_in_text(
                lowered_url,
                cls.LEGITIMATE_URL_POSITIVE_MARKERS,
            )
            negative_hits = cls._count_in_text(
                lowered_url,
                cls.LEGITIMATE_URL_NEGATIVE_MARKERS,
            )
            return positive_hits * 4 - negative_hits * 3
        if category == "spam_like":
            positive_hits = cls._count_in_text(
                lowered_url,
                cls.SPAM_URL_POSITIVE_MARKERS,
            )
            return positive_hits * 4

        positive_hits = cls._count_in_text(
            lowered_url,
            cls.PHISHING_URL_POSITIVE_MARKERS,
        )
        return positive_hits * 3

    @classmethod
    def score_text_window(cls, text: str) -> int:
        lowered_text = text.lower()
        message_hits = cls._count_in_text(lowered_text, cls.MESSAGE_MARKERS)
        guidance_hits = cls._count_in_text(lowered_text, cls.GUIDANCE_MARKERS)
        product_hits = cls._count_in_text(lowered_text, cls.PRODUCT_MARKERS)
        nav_hits = cls._count_in_text(lowered_text, cls.NAV_MARKERS)
        page_hits = cls._count_in_text(lowered_text, cls.PAGE_MARKERS)
        noise_hits = cls._count_in_text(lowered_text, cls.NOISE_MARKERS)
        score = message_hits * 4
        score += cls._keyword_bonus(
            lowered_text, ("bonjour", "cordialement", "service client"), 2
        )
        score += cls._keyword_bonus(
            lowered_text,
            ("mot de passe", "notification", "sms", "e-mail", "courrier", "compte"),
            2,
        )
        score -= guidance_hits * 2
        score -= product_hits * 3
        score -= nav_hits * 5
        score -= page_hits * 4
        score -= noise_hits * 4
        return score

    @classmethod
    def _extract_best_window(cls, segments: list[str]) -> str | None:
        if not segments:
            return None

        best_score = 0
        best_window: str | None = None
        for start in range(len(segments)):
            for size in range(1, 5):
                end = start + size
                if end > len(segments):
                    break
                window = " ".join(segments[start:end]).strip()
                if len(window) < cls.MIN_SEGMENT_LEN:
                    continue
                score = cls.score_text_window(window)
                if score > best_score:
                    best_score = score
                    best_window = window

        return None if best_window is None or best_score < 5 else best_window

    @classmethod
    def _split_segments(cls, text: str) -> list[str]:
        prepared = text
        for marker in cls.NAV_MARKERS + cls.PAGE_MARKERS:
            prepared = re.sub(
                re.escape(marker),
                f"\n{marker}\n",
                prepared,
                flags=re.IGNORECASE,
            )
        raw_segments = re.split(r"(?<=[.!?])\s+|\n+", prepared)
        segments = [
            cls._normalize_text(segment)
            for segment in raw_segments
            if cls._normalize_text(segment)
        ]
        return [segment for segment in segments if len(segment) >= cls.MIN_SEGMENT_LEN]

    @classmethod
    def _strip_known_noise(cls, text: str) -> str:
        cleaned_text = text
        for marker in cls.NAV_MARKERS + cls.PAGE_MARKERS + cls.NOISE_MARKERS:
            cleaned_text = re.sub(
                re.escape(marker),
                " ",
                cleaned_text,
                flags=re.IGNORECASE,
            )
        return re.sub(r"\s+", " ", cleaned_text).strip()

    @classmethod
    def _strip_soft_noise(cls, text: str) -> str:
        cleaned_text = text
        for marker in cls.NOISE_MARKERS:
            cleaned_text = re.sub(
                re.escape(marker),
                " ",
                cleaned_text,
                flags=re.IGNORECASE,
            )
        return re.sub(r"\s+", " ", cleaned_text).strip()

    @staticmethod
    def _count_in_text(text: str, markers: Iterable[str]) -> int:
        return len([marker for marker in markers if marker in text])

    @staticmethod
    def _keyword_bonus(text: str, markers: Iterable[str], weight: int) -> int:
        return sum(weight for marker in markers if marker in text)

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = html.unescape(text or "")
        normalized = normalized.replace("\xa0", " ")
        normalized = re.sub(r"(\n\s*){3,}", "\n\n", normalized)
        normalized = re.sub(r"[ \t]{2,}", " ", normalized)
        return normalized.strip()
