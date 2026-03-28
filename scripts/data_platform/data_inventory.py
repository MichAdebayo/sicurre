"""Full inventory of all data files with accurate row counts and label distributions."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

ROOT = str(Path(__file__).resolve().parents[2])

files = {
    "phishtank": "data/raw/api/phishtank/phishing-tank.csv",
    "bigquery": "data/raw/bigdata/bigquery/bigquery_phishing_en_4597_20260228.csv",
    "common_crawl": "data/raw/bigdata/common_crawl/common_crawl_fr_usable_28_20260228.csv",
    "combined_final_clean": "data/raw/csv/en/combined_final_clean.csv",
    "cybersectony_legit": "data/raw/csv/en/cybersectony_legit_6606_20260301.csv",
    "enron_hamspam": "data/raw/csv/en/enron_hamspam_28191_20260301.csv",
    "french_spamham": "data/raw/csv/fr/french_spamham_1000_20260301.csv",
    "kaggle_multi_fr": "data/raw/csv/fr/kaggle_multilingual_fr_4981_20260301.csv",
    "adapted_fr": "data/raw/db/adapted_fr_phishing_2400_20260228.csv",
    "synthetic_fr": "data/raw/db/synthetic_fr_emails_2863_20260228.csv",
    "certfr_reports": "data/raw/scraping/certfr/certfr_cti_reports_91_20260301.csv",
    "certfr_phishing": "data/raw/scraping/certfr/certfr_phishing_37_20260301.csv",
}

# Also check processed
processed = {
    "proc_adapted": "data/processed/adapted/adapted_clean_2145_20260301.csv",
    "proc_legitimate": "data/processed/legitimate/legitimate_clean_7461_20260301.csv",
    "proc_synthetic": "data/processed/synthetic/synthetic_clean_1747_20260301.csv",
}

print("=" * 80)
print("RAW DATA INVENTORY")
print("=" * 80)

for name, relpath in files.items():
    path = os.path.join(ROOT, relpath)
    try:
        df = pd.read_csv(path, low_memory=False)
        size_mb = os.path.getsize(path) / (1024 * 1024)
        cols = list(df.columns)
        print(f"\n--- {name} --- ({len(df):,} rows, {size_mb:.1f} MB)")
        print(f"  Columns: {cols}")
        if "label" in cols:
            print(f"  Labels: {df['label'].value_counts().to_dict()}")
        if "language" in cols:
            print(f"  Languages: {df['language'].value_counts().to_dict()}")
        if "source" in cols:
            src = df["source"].value_counts().to_dict()
            if len(src) <= 10:
                print(f"  Sources: {src}")
            else:
                print(f"  Sources: {len(src)} unique values")
    except Exception as e:
        print(f"\n--- {name} --- ERROR: {e}")

print("\n" + "=" * 80)
print("PROCESSED DATA INVENTORY")
print("=" * 80)

for name, relpath in processed.items():
    path = os.path.join(ROOT, relpath)
    try:
        df = pd.read_csv(path, low_memory=False)
        size_mb = os.path.getsize(path) / (1024 * 1024)
        print(f"\n--- {name} --- ({len(df):,} rows, {size_mb:.1f} MB)")
        if "label" in df.columns:
            print(f"  Labels: {df['label'].value_counts().to_dict()}")
        if "language" in df.columns:
            print(f"  Languages: {df['language'].value_counts().to_dict()}")
        if "source" in df.columns:
            print(f"  Sources: {df['source'].value_counts().to_dict()}")
    except Exception as e:
        print(f"\n--- {name} --- ERROR: {e}")
