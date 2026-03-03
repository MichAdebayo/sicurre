"""
Process raw FR sources and restructure data/processed/ into 3-class layout.

Target structure:
  data/processed/
  ├── phishing/
  │   ├── fr_phishing/     ← Real FR phishing (AFI, SAP phishing, CERT-FR)
  │   ├── adapted/         ← Existing adapted_clean (moved)
  │   ├── synthetic/       ← Existing synthetic_clean (moved)
  │   └── phishing_url/    ← PhishTank URLs (deduplicated)
  ├── spam/
  │   └── fr_spam_clean_*.csv  ← Kaggle FR spam + French SpamHam spam
  └── legitimate/
      ├── fr_legit/        ← Real FR legit (Kaggle ham, FrenchSpamHam ham, SAP legit)
      └── fr_synthetic/    ← Synthetic FR legit (split from existing legitimate_clean)

Processing pipeline (same as NB12):
  1. HTML entity decode + tag stripping
  2. Non-printable character removal
  3. Unicode NFC normalization
  4. Whitespace collapse
  5. PII anonymization (7 patterns)
  6. Length filtering (min 30, max 10K truncate)
  7. SHA-256 dedup (first 300 chars)
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd

# ── Constants ────────────────────────────────────────────────
MIN_TEXT_LEN: int = 30
MAX_TEXT_LEN: int = 10_000
DEDUP_HASH_LEN: int = 300
TODAY: str = date.today().strftime("%Y%m%d")

BASE = Path(".")
RAW = BASE / "data" / "raw"
PROC = BASE / "data" / "processed"

# ── PII regexes (RGPD compliance) ───────────────────────────
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

OUTPUT_COLS: list[str] = [
    "text",
    "label",
    "source",
    "language",
    "archetype",
    "text_len",
]


# ── Cleaning functions ───────────────────────────────────────
def anonymize_pii(text: str) -> str:
    """Replace PII with anonymization tokens."""
    text = _RE_EMAIL.sub("[EMAIL]", text)
    text = _RE_IBAN.sub("[IBAN]", text)
    text = _RE_SECU.sub("[SECU]", text)
    text = _RE_SIRET.sub("[SIRET]", text)
    text = _RE_PHONE_INTL.sub("[PHONE]", text)
    text = _RE_PHONE_FR.sub("[PHONE]", text)
    text = _RE_URL.sub("[URL]", text)
    return text


def clean_text(text: str) -> str:
    """Full NB12 cleaning pipeline on a single text field."""
    if not isinstance(text, str) or not text.strip():
        return ""
    text = html.unescape(text)
    text = _RE_HTML_TAGS.sub(" ", text)
    text = _RE_NON_PRINTABLE.sub("", text)
    text = unicodedata.normalize("NFC", text)
    text = _RE_MULTI_SPACE.sub(" ", text)
    text = _RE_MULTI_NEWLINE.sub("\n\n", text)
    text = text.strip()
    text = anonymize_pii(text)
    if len(text) > MAX_TEXT_LEN:
        text = text[:MAX_TEXT_LEN] + "…"
    return text


def process_df(df: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """Apply clean + filter + dedup to a DataFrame with 'text' column."""
    df = df.copy()
    df["text"] = df["text"].apply(clean_text)
    df["text_len"] = df["text"].str.len()
    # Filter too short
    before = len(df)
    df = df[df["text_len"] >= MIN_TEXT_LEN].reset_index(drop=True)
    dropped_short = before - len(df)
    # Dedup by SHA-256 of first 300 chars
    df["_hash"] = (
        df["text"]
        .str[:DEDUP_HASH_LEN]
        .apply(lambda t: hashlib.sha256(t.encode("utf-8", errors="ignore")).hexdigest())
    )
    before2 = len(df)
    df = (
        df.drop_duplicates(subset="_hash", keep="first")
        .drop(columns="_hash")
        .reset_index(drop=True)
    )
    dropped_dup = before2 - len(df)
    return df, dropped_short, dropped_dup


def save_csv(df: pd.DataFrame, path: Path, label_name: str) -> None:
    """Save DataFrame with standard columns, creating dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Ensure all output columns exist
    for col in OUTPUT_COLS:
        if col not in df.columns:
            df[col] = ""
    df[OUTPUT_COLS].to_csv(path, index=False)
    print(f"  ✅ Saved {path} ({len(df)} rows, {label_name})")


# ── Load & prepare sources ───────────────────────────────────
def load_afi() -> pd.DataFrame:
    """AFI French scam forum — 125 real phishing emails."""
    df = pd.read_csv(
        RAW / "scraping" / "afi_french" / "afi_french_scam_125_20260301.csv"
    )
    return pd.DataFrame(
        {
            "text": df["body"],
            "label": 0,  # Will be set to phishing label
            "source": "afi_french_forum",
            "language": "fr",
            "archetype": "",
        }
    )


def load_certfr() -> pd.DataFrame:
    """CERT-FR phishing alerts — 37 phishing-related advisory texts."""
    df = pd.read_csv(RAW / "scraping" / "certfr" / "certfr_phishing_37_20260301.csv")
    return pd.DataFrame(
        {
            "text": df["text"],
            "label": 0,  # Will be set to phishing label
            "source": "certfr_phishing",
            "language": "fr",
            "archetype": "",
        }
    )


def load_sap(label_filter: str) -> pd.DataFrame:
    """SAP Labs FR emails, filtered by label ('phishing' or 'legitimate')."""
    with open(RAW / "scraping" / "sap_labs_fr_emails_18.json") as f:
        data = json.load(f)
    emails = [e for e in data["emails"] if e["label"] == label_filter]
    return pd.DataFrame(
        {
            "text": [
                f"De: {e['sender']}\nObjet: {e['subject']}\n\n{e['body']}"
                for e in emails
            ],
            "label": 0,  # Set by caller
            "source": "sap_labs_blog",
            "language": "fr",
            "archetype": "",
        }
    )


def load_kaggle_fr(label_filter: str) -> pd.DataFrame:
    """Kaggle multilingual FR, filtered by label ('spam' or 'ham')."""
    df = pd.read_csv(RAW / "csv" / "fr" / "kaggle_multilingual_fr_4981_20260301.csv")
    df = df[df["label"] == label_filter].copy()
    df["archetype"] = ""
    return df


def load_french_spamham(label_filter: str) -> pd.DataFrame:
    """French SpamHam dataset, filtered by label ('spam' or 'ham')."""
    df = pd.read_csv(RAW / "csv" / "fr" / "french_spamham_1000_20260301.csv")
    df = df[df["label"] == label_filter].copy()
    df["archetype"] = ""
    return df


def load_phishtank() -> pd.DataFrame:
    """PhishTank verified phishing URLs."""
    df = pd.read_csv(RAW / "api" / "phishtank" / "phishing-tank.csv")
    # Only keep verified phishing URLs, deduplicate by URL
    df = df[df["verified"] == "yes"].copy()
    df = df.drop_duplicates(subset="url", keep="first").reset_index(drop=True)
    return df


# ── Main ─────────────────────────────────────────────────────
def main() -> None:
    print("=" * 60)
    print("SICURRE — Process & Restructure data/processed/")
    print("=" * 60)

    # ── 1. PHISHING / fr_phishing (real FR sources) ─────────
    print("\n📁 phishing/fr_phishing/ — Real FR phishing sources")

    # AFI (all 125 are phishing/scam)
    afi = load_afi()
    afi["label"] = 0  # phishing = 0 in 3-class schema
    print(f"  AFI loaded: {len(afi)} rows")

    # CERT-FR phishing alerts
    certfr = load_certfr()
    certfr["label"] = 0  # phishing
    print(f"  CERT-FR loaded: {len(certfr)} rows")

    # SAP phishing subset
    sap_phish = load_sap("phishing")
    sap_phish["label"] = 0  # phishing
    print(f"  SAP phishing loaded: {len(sap_phish)} rows")

    # Combine real FR phishing
    fr_phishing = pd.concat([afi, certfr, sap_phish], ignore_index=True)
    print(f"  Combined: {len(fr_phishing)} rows (pre-processing)")
    fr_phishing, short, dup = process_df(fr_phishing)
    print(
        f"  After processing: {len(fr_phishing)} rows (dropped: {short} short, {dup} dup)"
    )

    out = (
        PROC
        / "phishing"
        / "fr_phishing"
        / f"fr_phishing_clean_{len(fr_phishing)}_{TODAY}.csv"
    )
    save_csv(fr_phishing, out, "phishing")

    # ── 2. PHISHING / adapted (move existing + remap label) ─
    print("\n📁 phishing/adapted/ — Move existing adapted_clean")
    src_adapted = PROC / "adapted" / "adapted_clean_2145_20260301.csv"
    dst_adapted = PROC / "phishing" / "adapted" / "adapted_clean_2145_20260301.csv"
    dst_adapted.parent.mkdir(parents=True, exist_ok=True)
    if src_adapted.exists():
        df_adapted = pd.read_csv(src_adapted)
        df_adapted["label"] = 0  # Remap: old binary 1 → 3-class phishing=0
        df_adapted.to_csv(dst_adapted, index=False)
        print(f"  ✅ Copied + remapped label→0: {dst_adapted} ({len(df_adapted)} rows)")
    elif dst_adapted.exists():
        print(f"  ⏭️  Already at {dst_adapted}")
    else:
        print(f"  ⚠️  Source not found: {src_adapted}")

    # ── 3. PHISHING / synthetic (move existing + remap label)
    print("\n📁 phishing/synthetic/ — Move existing synthetic_clean")
    src_synth = PROC / "synthetic" / "synthetic_clean_1747_20260301.csv"
    dst_synth = PROC / "phishing" / "synthetic" / "synthetic_clean_1747_20260301.csv"
    dst_synth.parent.mkdir(parents=True, exist_ok=True)
    if src_synth.exists():
        df_synth = pd.read_csv(src_synth)
        df_synth["label"] = 0  # Remap: old binary 1 → 3-class phishing=0
        df_synth.to_csv(dst_synth, index=False)
        print(f"  ✅ Copied + remapped label→0: {dst_synth} ({len(df_synth)} rows)")
    elif dst_synth.exists():
        print(f"  ⏭️  Already at {dst_synth}")
    else:
        print(f"  ⚠️  Source not found: {src_synth}")

    # ── 4. PHISHING / phishing_url (PhishTank) ──────────────
    print("\n📁 phishing/phishing_url/ — PhishTank verified URLs")
    pt = load_phishtank()
    print(f"  Loaded: {len(pt)} verified unique URLs (from 56,071 raw)")
    out_pt = (
        PROC
        / "phishing"
        / "phishing_url"
        / f"phishtank_urls_clean_{len(pt)}_{TODAY}.csv"
    )
    out_pt.parent.mkdir(parents=True, exist_ok=True)
    # Keep relevant columns only, add timestamp
    pt_out = pt[["phish_id", "url", "submission_time", "target"]].copy()
    pt_out.to_csv(out_pt, index=False)
    print(f"  ✅ Saved {out_pt} ({len(pt_out)} rows)")

    # ── 5. SPAM (real FR spam) ──────────────────────────────
    print("\n📁 spam/ — Real FR spam")

    kaggle_spam = load_kaggle_fr("spam")
    kaggle_spam["label"] = 1  # spam = 1 in 3-class schema
    print(f"  Kaggle FR spam loaded: {len(kaggle_spam)} rows")

    fsh_spam = load_french_spamham("spam")
    fsh_spam["label"] = 1  # spam
    print(f"  French SpamHam spam loaded: {len(fsh_spam)} rows")

    fr_spam = pd.concat([kaggle_spam, fsh_spam], ignore_index=True)
    fr_spam["archetype"] = ""
    print(f"  Combined: {len(fr_spam)} rows (pre-processing)")
    fr_spam, short, dup = process_df(fr_spam)
    print(
        f"  After processing: {len(fr_spam)} rows (dropped: {short} short, {dup} dup)"
    )

    out_spam = PROC / "spam" / f"fr_spam_clean_{len(fr_spam)}_{TODAY}.csv"
    save_csv(fr_spam, out_spam, "spam")

    # ── 6. LEGITIMATE / fr_legit (real FR ham) ──────────────
    print("\n📁 legitimate/fr_legit/ — Real FR legitimate")

    kaggle_ham = load_kaggle_fr("ham")
    kaggle_ham["label"] = 2  # legitimate = 2 in 3-class schema
    print(f"  Kaggle FR ham loaded: {len(kaggle_ham)} rows")

    fsh_ham = load_french_spamham("ham")
    fsh_ham["label"] = 2  # legitimate
    print(f"  French SpamHam ham loaded: {len(fsh_ham)} rows")

    sap_legit = load_sap("legitimate")
    sap_legit["label"] = 2  # legitimate
    print(f"  SAP legit loaded: {len(sap_legit)} rows")

    fr_legit = pd.concat([kaggle_ham, fsh_ham, sap_legit], ignore_index=True)
    fr_legit["archetype"] = ""
    print(f"  Combined: {len(fr_legit)} rows (pre-processing)")
    fr_legit, short, dup = process_df(fr_legit)
    print(
        f"  After processing: {len(fr_legit)} rows (dropped: {short} short, {dup} dup)"
    )

    out_legit = (
        PROC / "legitimate" / "fr_legit" / f"fr_legit_clean_{len(fr_legit)}_{TODAY}.csv"
    )
    save_csv(fr_legit, out_legit, "legitimate")

    # ── 7. LEGITIMATE / fr_synthetic (split from existing) ──
    print("\n📁 legitimate/fr_synthetic/ — Synthetic FR legit (from NB11)")
    existing_legit = pd.read_csv(
        PROC / "legitimate" / "legitimate_clean_7461_20260301.csv"
    )
    fr_synth_legit = existing_legit[existing_legit["source"] == "synthetic_fr"].copy()
    fr_synth_legit["label"] = 2  # legitimate in 3-class schema
    print(f"  Extracted: {len(fr_synth_legit)} FR synthetic legit rows")

    out_synth_legit = (
        PROC
        / "legitimate"
        / "fr_synthetic"
        / f"fr_synthetic_legit_clean_{len(fr_synth_legit)}_{TODAY}.csv"
    )
    save_csv(fr_synth_legit, out_synth_legit, "legitimate")

    # ── 8. Clean up old flat structure ──────────────────────
    print("\n🧹 Cleaning up old flat structure…")
    old_dirs = [
        PROC / "adapted",
        PROC / "synthetic",
        PROC / "legitimate" / "legitimate_clean_7461_20260301.csv",
    ]
    # Remove old top-level files/dirs (but keep the new subfolders)
    old_adapted = PROC / "adapted"
    old_synthetic = PROC / "synthetic"
    old_legit_csv = PROC / "legitimate" / "legitimate_clean_7461_20260301.csv"

    # Remove old .gitkeep and flat CSVs from old locations
    for p in [
        old_adapted / ".gitkeep",
        old_adapted / "adapted_clean_2145_20260301.csv",
        old_synthetic / ".gitkeep",
        old_synthetic / "synthetic_clean_1747_20260301.csv",
    ]:
        if p.exists():
            p.unlink()
            print(f"  Removed {p}")

    # Remove old empty dirs (only if empty after file removal)
    for d in [old_adapted, old_synthetic]:
        if d.exists() and not any(d.iterdir()):
            d.rmdir()
            print(f"  Removed empty dir {d}")

    # Remove old legitimate flat CSV (keep dir since it now has subfolders)
    if old_legit_csv.exists():
        old_legit_csv.unlink()
        print(f"  Removed {old_legit_csv}")

    old_legit_gitkeep = PROC / "legitimate" / ".gitkeep"
    if old_legit_gitkeep.exists():
        old_legit_gitkeep.unlink()
        print(f"  Removed {old_legit_gitkeep}")

    # ── Summary ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("FINAL STRUCTURE")
    print("=" * 60)

    total_phishing = len(fr_phishing) + 2145 + 1747  # fr_phishing + adapted + synthetic
    total_spam = len(fr_spam)
    total_legit = len(fr_legit) + len(fr_synth_legit)

    print(
        f"""
data/processed/
├── phishing/
│   ├── fr_phishing/     {len(fr_phishing):>5} rows  (AFI + CERT-FR + SAP phishing)
│   ├── adapted/         2,145 rows  (existing adapted_clean)
│   ├── synthetic/       1,747 rows  (existing synthetic_clean)
│   └── phishing_url/   {len(pt_out):>5} rows  (PhishTank verified URLs)
├── spam/
│   └── fr_spam_clean   {len(fr_spam):>5} rows  (Kaggle FR + French SpamHam spam)
└── legitimate/
    ├── fr_legit/        {len(fr_legit):>5} rows  (Kaggle FR + French SpamHam + SAP legit)
    └── fr_synthetic/      {len(fr_synth_legit):>3} rows  (NB11 synthetic legit)

TOTALS (French data only):
  Phishing (label=0): {total_phishing:,} rows
  Spam (label=1):     {total_spam:,} rows
  Legitimate (label=2): {total_legit:,} rows
  Grand total:        {total_phishing + total_spam + total_legit:,} rows
  + PhishTank URLs:   {len(pt_out):,} (metadata, not email bodies)
"""
    )


if __name__ == "__main__":
    main()
