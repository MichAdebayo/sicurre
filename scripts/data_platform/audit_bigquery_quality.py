"""Audit BigQuery CSV for gibberish / non-text rows."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

CSV_PATH = Path("data/raw/bigdata/bigquery/bigquery_phishing_en_4597_20260228.csv")

df = pd.read_csv(CSV_PATH)
df["text"] = df["text"].astype(str)
df["text_len"] = df["text"].str.len()
df["word_count"] = df["text"].str.split().str.len()
df["alpha_ratio"] = df["text"].apply(
    lambda t: sum(c.isalpha() for c in t) / max(len(t), 1)
)
df["ascii_ratio"] = df["text"].apply(
    lambda t: sum(c.isascii() for c in t) / max(len(t), 1)
)

print(f"Total rows: {len(df):,}")
print(f"\n{'='*60}")
print("TEXT LENGTH STATS")
print(df["text_len"].describe().to_string())

print(f"\n{'='*60}")
print("ALPHA RATIO (% of chars that are letters)")
print(df["alpha_ratio"].describe().to_string())

print(f"\n{'='*60}")
print("GIBBERISH DETECTION")

# 1. Low alpha ratio (<40% letters)
low_alpha = df[df["alpha_ratio"] < 0.4]
print(f"\n[1] Rows with <40% alpha chars : {len(low_alpha):,}")

# 2. URL-only rows
url_only = df[df["text"].str.match(r"^https?://\S+$", na=False)]
print(f"[2] Rows that are just URLs    : {len(url_only):,}")

# 3. Non-ASCII heavy (encoded/binary)
non_ascii = df[df["ascii_ratio"] < 0.5]
print(f"[3] Rows with <50% ASCII       : {len(non_ascii):,}")

# 4. Base64-like blobs
b64_pat = re.compile(r"^[A-Za-z0-9+/=\s]{50,}$")
b64_rows = df[df["text"].apply(lambda t: bool(b64_pat.match(t)))]
print(f"[4] Base64-like blobs          : {len(b64_rows):,}")

# 5. Long but few words (encoded strings, hashes, etc.)
few_words = df[(df["text_len"] > 50) & (df["word_count"] < 5)]
print(f"[5] >50 chars but <5 words     : {len(few_words):,}")

# 6. HTML-heavy (lots of < and > tags still present)
html_heavy = df[df["text"].str.count("<") > 10]
print(f"[6] >10 HTML tags              : {len(html_heavy):,}")

# 7. Repeated char sequences (e.g. "aaaaaa..." or "======")
repeat_pat = re.compile(r"(.)\1{20,}")
repeated = df[df["text"].apply(lambda t: bool(repeat_pat.search(t)))]
print(f"[7] Repeated char runs (20+)   : {len(repeated):,}")

# Combined: any of the above flags
flagged = df[
    (df["alpha_ratio"] < 0.4)
    | df["text"].str.match(r"^https?://\S+$", na=False)
    | (df["ascii_ratio"] < 0.5)
    | df["text"].apply(lambda t: bool(b64_pat.match(t)))
    | ((df["text_len"] > 50) & (df["word_count"] < 5))
    | (df["text"].str.count("<") > 10)
    | df["text"].apply(lambda t: bool(repeat_pat.search(t)))
]
print(
    f"\n>>> TOTAL FLAGGED (any rule): {len(flagged):,} / {len(df):,} ({len(flagged)/len(df)*100:.1f}%)"
)

# Show samples from each category
print(f"\n{'='*60}")
print("SAMPLE FLAGGED ROWS (first 200 chars)")
print("=" * 60)

for idx, row in flagged.head(20).iterrows():
    flags = []
    if row["alpha_ratio"] < 0.4:
        flags.append("low-alpha")
    if re.match(r"^https?://\S+$", row["text"]):
        flags.append("url-only")
    if row["ascii_ratio"] < 0.5:
        flags.append("non-ascii")
    if b64_pat.match(row["text"]):
        flags.append("base64")
    if row["text_len"] > 50 and row["word_count"] < 5:
        flags.append("few-words")
    if row["text"].count("<") > 10:
        flags.append("html-heavy")
    if repeat_pat.search(row["text"]):
        flags.append("repeated")

    preview = row["text"][:200].replace("\n", "\\n")
    print(
        f"\n[Row {idx}] flags={flags} len={row['text_len']} words={row['word_count']} alpha={row['alpha_ratio']:.2f}"
    )
    print(f"  {preview}")

# Distribution of flagged by type
print(f"\n{'='*60}")
print("CLEAN vs FLAGGED SUMMARY")
clean = df[~df.index.isin(flagged.index)]
print(f"Clean rows  : {len(clean):,} ({len(clean)/len(df)*100:.1f}%)")
print(f"Flagged rows: {len(flagged):,} ({len(flagged)/len(df)*100:.1f}%)")
print(
    f"\nClean text length: avg={clean['text_len'].mean():.0f}, median={clean['text_len'].median():.0f}"
)
print(
    f"Flagged text len : avg={flagged['text_len'].mean():.0f}, median={flagged['text_len'].median():.0f}"
)
