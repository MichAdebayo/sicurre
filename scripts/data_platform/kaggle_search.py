"""Search & download Kaggle multilingual spam dataset."""

from __future__ import annotations
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[2]
load_dotenv(BASE / ".env")

# Verify Kaggle credentials are available (via env or ~/.kaggle/kaggle.json)
_kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
if not (os.environ.get("KAGGLE_USERNAME") or _kaggle_json.exists()):
    print(
        "Error: Kaggle credentials not found. Set KAGGLE_USERNAME/KAGGLE_KEY in .env or place kaggle.json",
        file=sys.stderr,
    )
    sys.exit(1)

from kaggle.api.kaggle_api_extended import KaggleApi

api = KaggleApi()
api.authenticate()
print("Kaggle auth OK")

# Search for the dataset
queries = [
    "multilingual spam sms",
    "spam ham french",
    "phishing email french",
    "spam email multilingual",
    "spam sms dataset",
    "french phishing",
]

for q in queries:
    results = api.dataset_list(search=q, sort_by="votes")
    if results is None:
        results = []
    print(f"\nQuery: {q!r} -> {len(results)} results")
    for ds in results[:5]:
        if ds and hasattr(ds, "ref"):
            print(f"  {ds.ref}")
