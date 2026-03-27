"""Download Kaggle datasets for Sicurre pipeline."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
load_dotenv(BASE / "backend" / ".env")

from kaggle.api.kaggle_api_extended import KaggleApi

api = KaggleApi()
api.authenticate()
print("Kaggle auth OK")

# Target directory
out_dir = Path("data/raw/csv")
out_dir.mkdir(parents=True, exist_ok=True)

# Download datasets
datasets = [
    "rajnathpatel/multilingual-spam-data",
    "kinoux/french-spamham-detection-free",
]

for slug in datasets:
    print(f"\n--- Downloading: {slug} ---")
    try:
        dest = out_dir / slug.split("/")[-1]
        dest.mkdir(parents=True, exist_ok=True)
        api.dataset_download_files(slug, path=str(dest), unzip=True)
        # List downloaded files
        for f in dest.iterdir():
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name} ({size_kb:.1f} KB)")
    except Exception as e:
        print(f"  ERROR: {e}")

print("\nDone.")
