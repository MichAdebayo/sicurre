# Data Summary — Sicurre

Running log of data extraction results, quality assessments, and pipeline outputs.
Updated after each notebook execution.

---

## 03 — BigQuery Extraction

**Date:** 2026-02-28  
**Notebook:** `notebooks/03_bigquery_extraction.ipynb`  
**Source:** `cybersectony/PhishingEmailDetectionv2.0` (HuggingFace → BigQuery)

### Source Dataset

| Metric | Value |
|--------|-------|
| Total rows | 120,000 |
| Columns | `content`, `label` |
| Labels | 0 (safe email): 6,809 · 1 (phishing email): 6,684 · 2 (safe URL): 53,157 · 3 (phishing URL): 53,350 |
| BigQuery table | `sicurre.sicurre_dataset.phishing_emails_en` |
| Table size | 44.8 MB |
| Region | `europe-west1` |

### Content Length Statistics (by label)

| Label | N | Avg len | Std len | Min | Max |
|-------|---|---------|---------|-----|-----|
| 0 (safe email) | 6,809 | 4,531 | 206,500 | 5 | 17,036,692 |
| 1 (phishing email) | 6,684 | 1,620 | 3,300 | 1 | 134,627 |
| 2 (safe URL) | 53,157 | 27 | 5 | 17 | 53 |
| 3 (phishing URL) | 53,350 | 46 | 58 | 14 | 4,274 |

### Extraction Results

| Metric | Value |
|--------|-------|
| Target | 5,000 phishing emails |
| Extracted | **4,597** (deduplicated) |
| Dedup method | `FARM_FINGERPRINT` + `QUALIFY ROW_NUMBER()` |
| Dedup removal | ~31% duplicates removed |
| Avg length | 1,752 chars |
| Min length | 51 chars |
| Max length | 134,627 chars |

### Export

| Metric | Value |
|--------|-------|
| File | `data/raw/bigquery/bigquery_phishing_en_4597_20260228.csv` |
| Size | 7.9 MB |
| Rows | 4,597 |
| Columns | `text`, `label`, `source`, `language` |
| Language | English (EN) — will be adapted to FR in notebook 05 |

### Cost

| Metric | Value |
|--------|-------|
| Total billed | 45 MB (0.044 GB) |
| Estimated cost | $0.00 USD |
| Free tier remaining | ~1,023.96 GB of 1,024 GB/month |

### Key Observations

- Labels 2 and 3 are **URLs** (avg 27–46 chars), not email bodies — only labels 0 and 1 are useful for text classification.
- Label 1 has 6,684 phishing emails, but after FARM_FINGERPRINT dedup only **4,597 unique** remain (~31% were duplicates).
- Some label 0 entries have extreme lengths (max 17M chars) — will need truncation in preprocessing.
- The dataset is **English-only** — cultural adaptation to French is required (notebook 05).

---

## 04 — Common Crawl Extraction

**Date:** 2026-02-28  
**Notebook:** `notebooks/04_common_crawl_extraction.ipynb`  
**Script:** `scripts/run_common_crawl.py`  
**Source:** Common Crawl Index API (`CC-MAIN-2025-08`)

### CC Index Query Results

| Category | Queries | Index Hits |
|----------|---------|-----------|
| Phishing (typosquatting) | 13 | **0** (all HTTP 404) |
| Legitimate FR | 7 | **323** (294 unique URLs) |
| **Total** | **20** | **323** |

**Key finding:** All 13 phishing domain patterns returned 0 results. Phishing sites are ephemeral — they're taken down before Common Crawl's monthly crawl reaches them. This confirms the hypothesis documented in the notebook.

### Legitimate FR Results (by label)

| Label | Hits |
|-------|------|
| legit_bank (BNP, CA, La Banque Postale) | 150 |
| legit_gov (Ameli, Impots, CAF) | 150 |
| legit_colis (Colissimo) | 23 |

### HTTP Status Distribution

| Status | Count |
|--------|-------|
| 200 | 221 |
| 301 | 43 |
| 404 | 37 |
| 500 | 10 |
| 401 | 5 |

### WARC Download & Extraction

| Metric | Value |
|--------|-------|
| Downloaded | 30 (capped at MAX_WARC_DOWNLOADS) |
| Extracted | 30 |
| Errors | 0 |
| Skipped (too short) | 0 |

### Data Quality Report

| Metric | Value |
|--------|-------|
| Total pages | 30 |
| Unique content hashes | 28 (6.7% duplicate rate) |
| Language: French | **30 (100%)** |
| Avg text length | 9,981 chars |
| Median text length | 10,000 chars (truncation cap) |
| Pages with ≥1 phishing keyword | 30 (100%) |
| Pages with ≥3 phishing keywords | 30 (100%) |
| Avg keywords/page | 3.1 |

### Signal-to-Noise Verdict

| Metric | Value |
|--------|-------|
| Usable (FR, deduplicated) | **28 pages** |
| Signal-to-Noise ratio | **93.3%** |
| Verdict | **GOOD SIGNAL** |

### Export

| File | Rows | Description |
|------|------|-------------|
| `data/raw/common_crawl/common_crawl_all_30_20260228.csv` | 30 | All extracted pages |
| `data/raw/common_crawl/common_crawl_fr_usable_28_20260228.csv` | 28 | French, deduplicated subset |
| `data/raw/common_crawl/quality_report_20260228.json` | — | Quality report metadata |

### Key Observations

1. **Phishing pages are NOT in Common Crawl** — all 13 typosquatting patterns returned 0 hits. This is expected and documented as a valid negative finding.
2. **Legitimate FR pages are well-covered** — 323 index hits across 7 queries. These are valuable as **ham (class 0)** reference data.
3. **100% French content** — every extracted page detected as French by langdetect.
4. **High keyword overlap** — legitimate banking/gov sites naturally contain phishing-related keywords (connexion, sécurité, identifiant), which is useful for training the model to distinguish legitimate banking language from phishing.
5. **BigQuery remains the primary big data source** for phishing emails. Common Crawl provides complementary legitimate FR web content.

---

<!-- Add new extraction summaries below this line -->
