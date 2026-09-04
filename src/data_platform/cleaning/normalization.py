from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from dataclasses import dataclass

MIN_TEXT_LEN = 30
MAX_TEXT_LEN = 10_000
DEDUP_HASH_LEN = 300

REDACTION_TOKENS = (
    "[EMAIL]",
    "[PHONE]",
    "[IBAN]",
    "[SECU]",
    "[SIRET]",
    "[URL]",
)

_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_RE_PHONE_FR = re.compile(r"\b0[1-9][ .-]?(?:\d{2}[ .-]?){4}\b")
_RE_PHONE_INTL = re.compile(r"\+\d{1,3}[\s.-]?\d{1,4}[\s.-]?(?:\d{2,4}[\s.-]?){2,4}")
_RE_IBAN = re.compile(r"\bFR\d{2}[\s]?(?:\d{4}[\s]?){5}\d{3}\b")
_RE_SECU = re.compile(r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b")
_RE_SIRET = re.compile(r"\b\d{3}\s?\d{3}\s?\d{3}\s?\d{5}\b")
_RE_URL = re.compile(r"https?://[^\s<>\"')]+|www\.[^\s<>\"')]+", re.IGNORECASE)
_RE_HTML_TAGS = re.compile(r"<[^>]+>")
_RE_MULTI_NEWLINE = re.compile(r"\n{3,}")
_RE_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_RE_NON_PRINTABLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


@dataclass(frozen=True, slots=True)
class NormalizedTextArtifact:
    cleaned_text: str
    text_length: int
    text_sha256: str
    dedup_sha256: str
    contains_redaction_tokens: bool
    is_usable: bool
    rejection_reason: str | None


def anonymize_pii(text: str) -> str:
    text = _RE_EMAIL.sub("[EMAIL]", text)
    text = _RE_IBAN.sub("[IBAN]", text)
    text = _RE_SECU.sub("[SECU]", text)
    text = _RE_SIRET.sub("[SIRET]", text)
    text = _RE_PHONE_INTL.sub("[PHONE]", text)
    text = _RE_PHONE_FR.sub("[PHONE]", text)
    text = _RE_URL.sub("[URL]", text)
    return text


def clean_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        return ""

    cleaned = html.unescape(text)
    cleaned = cleaned.replace("\xa0", " ")
    cleaned = _RE_HTML_TAGS.sub(" ", cleaned)
    cleaned = _RE_NON_PRINTABLE.sub("", cleaned)
    cleaned = unicodedata.normalize("NFC", cleaned)
    cleaned = _RE_MULTI_SPACE.sub(" ", cleaned)
    cleaned = _RE_MULTI_NEWLINE.sub("\n\n", cleaned)
    cleaned = cleaned.strip()
    cleaned = anonymize_pii(cleaned)
    if len(cleaned) > MAX_TEXT_LEN:
        cleaned = cleaned[:MAX_TEXT_LEN] + "..."
    return cleaned


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dedup_sha256(text: str) -> str:
    return hashlib.sha256(text[:DEDUP_HASH_LEN].encode("utf-8")).hexdigest()


class TextNormalizationService:
    def normalize_text(self, text: str) -> NormalizedTextArtifact:
        cleaned_text = clean_text(text)
        text_length = len(cleaned_text)
        contains_redaction_tokens = any(
            token in cleaned_text for token in REDACTION_TOKENS
        )

        if not cleaned_text:
            return NormalizedTextArtifact(
                cleaned_text="",
                text_length=0,
                text_sha256=text_sha256(""),
                dedup_sha256=dedup_sha256(""),
                contains_redaction_tokens=False,
                is_usable=False,
                rejection_reason="empty_after_cleaning",
            )

        rejection_reason = None
        is_usable = True
        if text_length < MIN_TEXT_LEN:
            is_usable = False
            rejection_reason = "text_too_short"

        return NormalizedTextArtifact(
            cleaned_text=cleaned_text,
            text_length=text_length,
            text_sha256=text_sha256(cleaned_text),
            dedup_sha256=dedup_sha256(cleaned_text),
            contains_redaction_tokens=contains_redaction_tokens,
            is_usable=is_usable,
            rejection_reason=rejection_reason,
        )
