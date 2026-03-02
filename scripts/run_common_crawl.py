"""Run Common Crawl extraction — standalone script equivalent of notebook 04."""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd
from bs4 import BeautifulSoup
from langdetect import detect, LangDetectException
from warcio.archiveiterator import ArchiveIterator

# ── Configuration ────────────────────────────────────────────────────
CC_INDEX_URL: str = "https://index.commoncrawl.org/CC-MAIN-2025-08-index"
OUTPUT_DIR: Path = Path("data/raw/bigdata/common_crawl")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MAX_RESULTS_PER_QUERY: int = 50
MAX_WARC_DOWNLOADS: int = 30
MIN_TEXT_LENGTH: int = 100
MAX_TEXT_LENGTH: int = 10_000
REQUEST_TIMEOUT: int = 30
CC_WARC_BASE: str = "https://data.commoncrawl.org/"

print(f"CC Index    : {CC_INDEX_URL}")
print(f"Output dir  : {OUTPUT_DIR.resolve()}")
print(f"Max results : {MAX_RESULTS_PER_QUERY}/query")
print(f"Max WARCs   : {MAX_WARC_DOWNLOADS}")


# ── Helpers ──────────────────────────────────────────────────────────
def query_cc_index(
    url_pattern: str, *, max_results: int = MAX_RESULTS_PER_QUERY
) -> list[dict]:
    params = {"url": url_pattern, "output": "json", "limit": str(max_results)}
    try:
        resp = httpx.get(
            CC_INDEX_URL, params=params, timeout=REQUEST_TIMEOUT, follow_redirects=True
        )
        resp.raise_for_status()
        records = []
        records.extend(
            json.loads(line) for line in resp.text.strip().split("\n") if line.strip()
        )
        return records
    except httpx.HTTPStatusError as e:
        print(f"  HTTP {e.response.status_code} for '{url_pattern}'")
        return []
    except Exception as e:
        print(f"  Error: {e}")
        return []


def fetch_warc_record(filename: str, offset: int, length: int) -> bytes | None:
    end = offset + length - 1
    url = f"{CC_WARC_BASE}{filename}"
    headers = {"Range": f"bytes={offset}-{end}"}
    try:
        resp = httpx.get(
            url, headers=headers, timeout=REQUEST_TIMEOUT, follow_redirects=True
        )
        return resp.content if resp.status_code in (200, 206) else None
    except Exception:
        return None


def extract_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "meta", "link", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_language_safe(text: str) -> str:
    try:
        return detect(text[:1000])
    except LangDetectException:
        return "unknown"


# ── 1. Connectivity test ────────────────────────────────────────────
print("\n== 1. Testing CC Index API ==")
if test := query_cc_index("fr.wikipedia.org/wiki/Phishing", max_results=1):
    print(f"  API reachable -- got {len(test)} result(s)")
    print(f"  Sample URL: {test[0].get('url', 'N/A')}")
else:
    print("  API returned 0 results or unreachable")

# ── 2. Define queries ───────────────────────────────────────────────
PHISHING_QUERIES = [
    {"pattern": "*.bnp-paribas-secure.*", "label": "phishing_bank"},
    {"pattern": "*.credit-agricole-login.*", "label": "phishing_bank"},
    {"pattern": "*.la-banque-postale-verification.*", "label": "phishing_bank"},
    {"pattern": "*.societe-generale-secure.*", "label": "phishing_bank"},
    {"pattern": "*.connexion-securisee.fr*", "label": "phishing_generic"},
    {"pattern": "*.verification-compte.*", "label": "phishing_generic"},
    {"pattern": "*.mise-a-jour-securite.*", "label": "phishing_generic"},
    {"pattern": "*.colissimo-suivi.*", "label": "phishing_colis"},
    {"pattern": "*.chronopost-livraison.*", "label": "phishing_colis"},
    {"pattern": "*.la-poste-colis.*", "label": "phishing_colis"},
    {"pattern": "*.ameli-remboursement.*", "label": "phishing_gov"},
    {"pattern": "*.impots-gouv-fr.*", "label": "phishing_gov"},
    {"pattern": "*.caf-allocation.*", "label": "phishing_gov"},
]

LEGITIMATE_QUERIES = [
    {"pattern": "www.mabanque.bnpparibas/*", "label": "legit_bank"},
    {"pattern": "www.credit-agricole.fr/*", "label": "legit_bank"},
    {"pattern": "www.labanquepostale.fr/*", "label": "legit_bank"},
    {"pattern": "www.ameli.fr/*", "label": "legit_gov"},
    {"pattern": "www.impots.gouv.fr/*", "label": "legit_gov"},
    {"pattern": "www.caf.fr/*", "label": "legit_gov"},
    {"pattern": "www.colissimo.fr/*", "label": "legit_colis"},
]

print(f"\nPhishing queries  : {len(PHISHING_QUERIES)}")
print(f"Legitimate queries : {len(LEGITIMATE_QUERIES)}")

# ── 3. Execute queries ──────────────────────────────────────────────
print("\n== 3. Querying CC Index ==")
all_queries = [
    *[(q, "phishing") for q in PHISHING_QUERIES],
    *[(q, "legitimate") for q in LEGITIMATE_QUERIES],
]
all_records: list[dict] = []

for query_def, category in all_queries:
    pattern = query_def["pattern"]
    label = query_def["label"]
    records = query_cc_index(pattern, max_results=MAX_RESULTS_PER_QUERY)
    for rec in records:
        rec["_category"] = category
        rec["_label"] = label
        rec["_query"] = pattern
    all_records.extend(records)
    status = f"{len(records):3d} results" if records else "  0 results"
    print(f"  [{category:10s}] {pattern:45s} -> {status}")
    time.sleep(0.5)

print(f"\nTotal index records: {len(all_records)}")

# ── 4. Inspect ──────────────────────────────────────────────────────
if not all_records:
    print("\n== NO RECORDS FOUND ==")
    print("  This is expected -- phishing domains are short-lived.")
    print("  Common Crawl may not have captured them.")
    print("  This is itself a valuable finding for the rapport.")
    df_index = pd.DataFrame()
else:
    df_index = pd.DataFrame(all_records)
    print(f"\n== Index Results Summary ==")
    print(f"Total records     : {len(df_index):,}")
    print(f"Unique URLs       : {df_index['url'].nunique():,}")
    print(f"\n== By Category ==")
    print(df_index["_category"].value_counts().to_string())
    print(f"\n== By Label ==")
    print(df_index["_label"].value_counts().to_string())
    if "status" in df_index.columns:
        print(f"\n== HTTP Status ==")
        print(df_index["status"].value_counts().head(5).to_string())
    if "mime" in df_index.columns:
        print(f"\n== MIME Types ==")
        print(df_index["mime"].value_counts().head(5).to_string())

    # Preview URLs
    print("\n== Sample URLs by Category ==")
    for cat in df_index["_category"].unique():
        subset = df_index[df_index["_category"] == cat]
        print(f"\n  {cat.upper()} ({len(subset)} records):")
        for url in subset["url"].head(5):
            print(f"   {url[:100]}")

# ── 5. Download WARC records ────────────────────────────────────────
extracted_pages: list[dict] = []
download_errors: int = 0
skipped_short: int = 0

if not df_index.empty:
    df_download = df_index.copy()
    if "status" in df_download.columns:
        df_download = df_download[df_download["status"].astype(str) == "200"]
    if "mime" in df_download.columns:
        df_download = df_download[
            df_download["mime"].str.contains("html", case=False, na=False)
        ]

    df_download = df_download.head(MAX_WARC_DOWNLOADS)
    print(f"\n== 5. Downloading {len(df_download)} WARC records ==")

    for i, (_, row) in enumerate(df_download.iterrows()):
        warc_data = fetch_warc_record(
            filename=row["filename"],
            offset=int(row["offset"]),
            length=int(row["length"]),
        )
        if warc_data is None:
            download_errors += 1
            continue

        try:
            stream = io.BytesIO(warc_data)
            for record in ArchiveIterator(stream):
                if record.rec_type == "response":
                    html = (
                        record.content_stream().read().decode("utf-8", errors="replace")
                    )
                    text = extract_text_from_html(html)
                    if len(text) < MIN_TEXT_LENGTH:
                        skipped_short += 1
                        continue
                    if len(text) > MAX_TEXT_LENGTH:
                        text = text[:MAX_TEXT_LENGTH]
                    lang = detect_language_safe(text)
                    extracted_pages.append(
                        {
                            "url": row["url"],
                            "text": text,
                            "text_length": len(text),
                            "language": lang,
                            "category": row["_category"],
                            "label": row["_label"],
                            "query": row["_query"],
                            "content_hash": hashlib.sha256(text.encode()).hexdigest()[
                                :16
                            ],
                        }
                    )
        except Exception:
            download_errors += 1
            continue

        if (i + 1) % 10 == 0:
            print(
                f"  [{i+1}/{len(df_download)}] extracted: {len(extracted_pages)}, errors: {download_errors}"
            )
        time.sleep(0.3)

    print(f"\n== Download Summary ==")
    print(f"   Downloaded    : {len(df_download)}")
    print(f"   Extracted     : {len(extracted_pages)}")
    print(f"   Errors        : {download_errors}")
    print(f"   Skipped short : {skipped_short}")

# ── 6. Quality Assessment ───────────────────────────────────────────
PHISHING_KEYWORDS_FR = [
    "mot de passe",
    "identifiant",
    "connexion",
    "verification",
    "securite",
    "compte bloque",
    "urgent",
    "confirmer",
    "cliquez ici",
    "mettre a jour",
    "remboursement",
    "carte bancaire",
    "numero de carte",
    "code secret",
    "livraison",
    "colis",
    "frais de douane",
]

if extracted_pages:
    df_pages = pd.DataFrame(extracted_pages)

    print("\n===========================================")
    print("  DATA QUALITY REPORT -- Common Crawl")
    print("===========================================")

    print(f"\n== Overview ==")
    print(f"   Total pages extracted : {len(df_pages)}")
    print(f"   Unique content hashes : {df_pages['content_hash'].nunique()}")
    dedup_rate = 1 - df_pages["content_hash"].nunique() / max(len(df_pages), 1)
    print(f"   Duplicate rate        : {dedup_rate:.1%}")

    print(f"\n== Language Distribution ==")
    lang_counts = df_pages["language"].value_counts()
    for lang, count in lang_counts.items():
        pct = count / len(df_pages) * 100
        marker = " <-- target" if lang == "fr" else ""
        print(f"   {lang:8s}: {count:4d} ({pct:5.1f}%){marker}")
    fr_count = lang_counts.get("fr", 0)
    fr_pct = fr_count / max(len(df_pages), 1) * 100
    print(f"\n   French content: {fr_count} pages ({fr_pct:.1f}%)")

    print(f"\n== Text Length (chars) ==")
    print(f"   Mean   : {df_pages['text_length'].mean():.0f}")
    print(f"   Median : {df_pages['text_length'].median():.0f}")
    print(f"   Min    : {df_pages['text_length'].min()}")
    print(f"   Max    : {df_pages['text_length'].max():,}")

    print(f"\n== By Category ==")
    print(
        df_pages.groupby("category")
        .agg(
            count=("text", "count"),
            fr_count=("language", lambda x: (x == "fr").sum()),
            avg_length=("text_length", "mean"),
        )
        .to_string()
    )

    # Keyword analysis
    def count_phishing_keywords(text: str) -> int:
        return sum(kw in text.lower() for kw in PHISHING_KEYWORDS_FR)

    df_pages["keyword_hits"] = df_pages["text"].apply(count_phishing_keywords)
    print(f"\n== Phishing Keyword Analysis ==")
    print(f"   Pages with >=1 keyword  : {(df_pages['keyword_hits'] >= 1).sum()}")
    print(f"   Pages with >=3 keywords : {(df_pages['keyword_hits'] >= 3).sum()}")
    print(f"   Avg keywords/page       : {df_pages['keyword_hits'].mean():.1f}")
    print(f"\n== Keyword Hits by Category ==")
    print(
        df_pages.groupby("category")["keyword_hits"]
        .agg(["mean", "max", "sum"])
        .to_string()
    )

    # Signal-to-noise
    df_usable = df_pages[
        (df_pages["language"] == "fr") & (df_pages["text_length"] >= MIN_TEXT_LENGTH)
    ].drop_duplicates(subset="content_hash")

    total = len(df_pages)
    usable = len(df_usable)
    ratio = usable / max(total, 1) * 100

    print(f"\n===========================================")
    print(f"  SIGNAL-TO-NOISE VERDICT")
    print(f"===========================================")
    print(f"   Total extracted     : {total}")
    print(f"   Usable (FR, dedup)  : {usable}")
    print(f"   Signal-to-Noise     : {ratio:.1f}%")
    if ratio >= 50:
        print(f"\n   GOOD SIGNAL -- worth including in the pipeline")
    elif ratio >= 20:
        print(f"\n   MODERATE SIGNAL -- include with careful filtering")
    else:
        print(f"\n   LOW SIGNAL -- Common Crawl adds little value for this use case")
        print(
            f"      This is expected: phishing pages are ephemeral and rarely crawled."
        )
        print(
            f"      Document this finding in the rapport -- it shows rigorous evaluation."
        )

    # Export
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    full_path = OUTPUT_DIR / f"common_crawl_all_{len(df_pages)}_{timestamp}.csv"
    df_pages.to_csv(full_path, index=False, encoding="utf-8")
    print(f"\nFull export    : {full_path} ({len(df_pages)} rows)")

    if not df_usable.empty:
        usable_path = (
            OUTPUT_DIR / f"common_crawl_fr_usable_{len(df_usable)}_{timestamp}.csv"
        )
        df_usable.to_csv(usable_path, index=False, encoding="utf-8")
        print(f"Usable FR only : {usable_path} ({len(df_usable)} rows)")

    report = {
        "extraction_date": timestamp,
        "cc_index": CC_INDEX_URL,
        "total_queries": len(PHISHING_QUERIES) + len(LEGITIMATE_QUERIES),
        "total_index_hits": 0 if df_index.empty else len(df_index),
        "total_downloaded": min(
            MAX_WARC_DOWNLOADS, len(df_download) if "df_download" in dir() else 0
        ),
        "total_extracted": len(df_pages),
        "download_errors": download_errors,
        "usable_french": len(df_usable),
        "language_distribution": df_pages["language"].value_counts().to_dict(),
        "category_distribution": df_pages["category"].value_counts().to_dict(),
    }
    report_path = OUTPUT_DIR / f"quality_report_{timestamp}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"Quality report : {report_path}")

else:
    print("\n== NO PAGES EXTRACTED ==")
    print("  Common Crawl returned 0 usable records.")
    print("  This is itself a valid finding for the certification report.")
    print("  Phishing sites are ephemeral -- crawlers rarely reach them in time.")

print("\n== DONE ==")
