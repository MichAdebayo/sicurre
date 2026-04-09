#!/usr/bin/env python3
"""Filter AFI scraped data to French-only emails and produce quality stats."""

import csv
from collections import Counter
from pathlib import Path

INPUT = Path("data/raw/scraping/afi_french/afi_french_scam_emails_v2.csv")
OUTPUT = Path("data/raw/scraping/afi_french/afi_french_only_125.csv")

with open(INPUT, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames or []
    all_rows = list(reader)

print(f"Total messages: {len(all_rows)}")

# Filter French
fr_rows = [r for r in all_rows if r["is_french"] == "True"]
print(f"French messages: {len(fr_rows)}")

# Write filtered CSV
with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for row in fr_rows:
        writer.writerow(row)

print(f"\nOutput: {OUTPUT}")

# Stats
print(f"\n=== Statistics ===")
print(f"Unique thread IDs: {len({r['thread_id'] for r in fr_rows})}")
print(
    f"Avg body length: {sum(int(r['body_length']) for r in fr_rows) / len(fr_rows):.0f} chars"
)
print(f"Min body length: {min(int(r['body_length']) for r in fr_rows)} chars")
print(f"Max body length: {max(int(r['body_length']) for r in fr_rows)} chars")

# Slug language breakdown
slug_langs = Counter(r["slug_lang"] for r in fr_rows)
print(f"\nSlug language breakdown:")
for lang, count in slug_langs.most_common():
    print(f"  {lang}: {count}")

# Sample French emails
print(f"\n=== Sample French email bodies ===")
for i, r in enumerate(fr_rows[:5]):
    body = r["body"]
    # Check if it has email headers
    has_headers = any(
        h in body[:200] for h in ["From:", "Subject:", "Return-Path:", "Date:"]
    )
    print(f"\n[{i+1}] Title: {r['title'][:60]}")
    print(f"    Headers present: {has_headers}")
    print(f"    Body length: {r['body_length']} chars")
    # First 200 chars of actual content (skip headers)
    lines = body.split("\n")
    content_start = 0
    for j, line in enumerate(lines):
        if line.startswith(("Bonjour", "Cher", "Chère", "Monsieur", "Madame", "Salut")):
            content_start = j
            break
    content = "\n".join(lines[content_start : content_start + 5])
    print(f"    Content preview: {content[:200]}")
