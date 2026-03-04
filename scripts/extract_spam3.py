"""
Extract French phishing emails from Spam_3.txt (colleague's mailbox export).

Spam_3.txt is a plain-text dump of 100 emails (35,717 lines). Nearly all French
emails are brand-impersonation phishing (LIDL, Vinci, FedEx, Carrefour, etc.).
Only 1 (MedChemExpress) is genuine spam. Non-French emails are skipped.

Steps:
  1. Parse email boundaries (From: headers)
  2. Extract subject + body
  3. Strip HTML (BeautifulSoup or regex)
  4. Language detection → keep French only
  5. Label as phishing (0) except MedChemExpress → spam (1)
  6. Run through NB12 pipeline (clean_text, anonymize, deduplicate)
  7. Save to data/processed/phishing/spam3_extract/

Usage:
  python scripts/extract_spam3.py
"""

from __future__ import annotations

import html
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from langdetect import detect, detect_langs, LangDetectException

# Add scripts/ to path for NB12 imports
sys.path.insert(0, str(Path(__file__).resolve().parent))
from process_restructure_data import (
    OUTPUT_COLS,
    clean_text,
    process_df,
    save_csv,
)

# ── Constants ──────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent.parent
SPAM3_PATH = BASE / "Spam_3.txt"
OUTPUT_DIR = BASE / "data" / "processed" / "phishing" / "spam3_extract"
TODAY = date.today().strftime("%Y%m%d")

# Known French brand impersonation keywords — if subject contains these,
# force-include even if langdetect is uncertain
FR_BRAND_KEYWORDS = {
    "lidl",
    "vinci",
    "autoroute",
    "fedex",
    "colis",
    "livraison",
    "carrefour",
    "leroy",
    "merlin",
    "manomano",
    "macbook",
    "iphone",
    "coffret",
    "sécurité",
    "gratuit",
    "sondage",
    "enquête",
    "félicitations",
    "récompense",
    "confirmation",
    "prêt",
    "expédié",
    "sélectionné",
    "gagner",
    "cadeau",
    "outils",
    "sephora",
    "décathlon",
    "decathlon",
    "dpd",
    "chronopost",
    "suivre",
    "préparation",
    "disponible",
    "rasoir",
    "braun",
    "ryobi",
    "makita",
    "dior",
    "lancôme",
    "moulinex",
    "cookeo",
    "bouygues",
    "werckmann",
    "pharmacie",
    "oral-b",
}

# Keywords that indicate genuine spam (not phishing)
SPAM_KEYWORDS = {"medchemexpress", "medchem"}


def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities from text using BeautifulSoup."""
    # First pass: remove style/script blocks before parsing
    text = re.sub(
        r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(
        r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE
    )
    # Remove HTML comments
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    # Remove MSO conditional blocks
    text = re.sub(
        r"<!\[if.*?\]>.*?<!\[endif\]>", " ", text, flags=re.DOTALL | re.IGNORECASE
    )

    # Parse with BeautifulSoup
    soup = BeautifulSoup(text, "html.parser")
    # Get text content
    plain = soup.get_text(separator=" ")

    # Decode any remaining HTML entities
    plain = html.unescape(plain)
    # Remove excessive URLs (tracking links with long base64)
    plain = re.sub(r"https?://\S{80,}", "[URL]", plain)
    # Remove base64-like strings (tracking pixels, encoded params)
    plain = re.sub(r"[A-Za-z0-9+/=]{60,}", "", plain)
    # Collapse whitespace
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain


def parse_emails(filepath: Path) -> list[dict[str, str]]:
    """Parse Spam_3.txt into individual emails with subject + body."""
    content = filepath.read_text(encoding="utf-8", errors="replace")

    # Split on "   From: " headers (3 leading spaces)
    parts = re.split(r"(?=\s{3}From:\s)", content)

    emails: list[dict[str, str]] = []
    for part in parts:
        part = part.strip()
        if not part or not part.startswith("From:"):
            # Also handle leading whitespace
            cleaned = part.lstrip()
            if not cleaned.startswith("From:"):
                continue
            part = cleaned

        # Extract subject
        subject_match = re.search(r"^Subject:\s*(.+?)$", part, re.MULTILINE)
        subject = subject_match.group(1).strip() if subject_match else ""

        # Extract body (everything after the header separator line of dashes)
        body_match = re.search(r"^-{10,}\s*\n(.*)", part, re.MULTILINE | re.DOTALL)
        body = body_match.group(1).strip() if body_match else ""

        if not body and not subject:
            continue

        # Strip HTML from body
        body_clean = strip_html(body)

        # Combine subject + body for classification
        full_text = f"{subject}\n{body_clean}" if subject else body_clean

        emails.append(
            {
                "subject": subject,
                "body": body_clean,
                "text": full_text,
            }
        )

    return emails


def detect_french(text: str, subject: str = "") -> bool:
    """Detect if text is French using langdetect + keyword fallback.

    Many Spam_3.txt emails have French content buried in HTML remnants.
    We use both langdetect and a keyword-based heuristic for recall.
    """
    combined = f"{subject} {text}"
    combined_lower = combined.lower()

    # Heuristic: check if subject or body contains known FR brand keywords
    has_fr_keywords = any(kw in combined_lower for kw in FR_BRAND_KEYWORDS)

    try:
        # Try detection on combined subject + first 1000 chars of body
        sample = combined[:1000]
        if len(sample) < 15:
            return has_fr_keywords

        langs = detect_langs(sample)
        for lang_prob in langs:
            if lang_prob.lang == "fr" and lang_prob.prob > 0.15:
                return True

        # If langdetect says not French but we have strong FR brand keywords,
        # try on just the subject (which is usually cleanly French)
        if has_fr_keywords and subject:
            try:
                subject_lang = detect(subject)
                if subject_lang == "fr":
                    return True
            except LangDetectException:
                pass

        # Last resort: strong keyword presence = French
        if has_fr_keywords:
            fr_word_count = sum(1 for kw in FR_BRAND_KEYWORDS if kw in combined_lower)
            if fr_word_count >= 2:
                return True

    except LangDetectException:
        return has_fr_keywords

    return False


def classify_email(text: str) -> int:
    """Classify email: 0=phishing, 1=spam."""
    text_lower = text.lower()
    for kw in SPAM_KEYWORDS:
        if kw in text_lower:
            return 1  # spam
    return 0  # phishing (default for Spam_3 — nearly all are brand impersonation)


def main() -> None:
    """Extract, filter, classify, and process Spam_3.txt emails."""
    print(f"Reading {SPAM3_PATH}...")
    emails = parse_emails(SPAM3_PATH)
    print(f"  Parsed {len(emails)} raw emails")

    # Filter French emails
    french_emails: list[dict[str, str | int]] = []
    skipped_subjects: list[str] = []
    for em in emails:
        if detect_french(em["text"], em.get("subject", "")):
            label = classify_email(em["text"])
            french_emails.append(
                {
                    "text": em["text"],
                    "label": label,
                }
            )
        else:
            skipped_subjects.append(em.get("subject", "(no subject)")[:80])

    print(f"  French emails: {len(french_emails)}")
    print(f"  Skipped (non-French): {len(skipped_subjects)}")
    if skipped_subjects:
        print("  Skipped subjects (first 10):")
        for s in skipped_subjects[:10]:
            print(f"    - {s}")
    phishing_count = sum(1 for e in french_emails if e["label"] == 0)
    spam_count = sum(1 for e in french_emails if e["label"] == 1)
    print(f"  Phishing: {phishing_count}, Spam: {spam_count}")

    if not french_emails:
        print("No French emails found. Exiting.")
        return

    # Build DataFrame
    df = pd.DataFrame(french_emails)
    df["source"] = "spam3_inbox"
    df["language"] = "fr"
    df["archetype"] = ""

    # ── Separate phishing and spam ──
    df_phishing = df[df["label"] == 0].copy()
    df_spam = df[df["label"] == 1].copy()

    # Process phishing through NB12 pipeline
    if not df_phishing.empty:
        print(f"\nProcessing {len(df_phishing)} phishing emails through NB12...")
        df_phishing_clean, dropped_short, dropped_dup = process_df(df_phishing)

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        outpath = (
            OUTPUT_DIR / f"spam3_phishing_clean_{len(df_phishing_clean)}_{TODAY}.csv"
        )
        save_csv(df_phishing_clean, outpath, label_name="phishing")
        print(f"  Dropped: {dropped_short} short, {dropped_dup} dups")

    # Process spam through NB12 pipeline
    if not df_spam.empty:
        print(f"\nProcessing {len(df_spam)} spam emails through NB12...")
        df_spam_clean, dropped_short, dropped_dup = process_df(df_spam)

        spam_dir = BASE / "data" / "processed" / "spam" / "spam3_extract"
        spam_dir.mkdir(parents=True, exist_ok=True)
        outpath = spam_dir / f"spam3_spam_clean_{len(df_spam_clean)}_{TODAY}.csv"
        save_csv(df_spam_clean, outpath, label_name="spam")
        print(f"  Dropped: {dropped_short} short, {dropped_dup} dups")

    print("\nDone.")


if __name__ == "__main__":
    main()
