# Base Ingestion — Reference Document

**Purpose**: Deterministic, one-time population of `sicurre.db` from all frozen
source data.  Every source has a `*-ingest-base` Makefile target that can be
replayed on a fresh database to reproduce the exact same dataset composition
used to train the final model — as long as no new files are added to R2 or
local storage after the manifest was generated.

**Guiding principles**

| Principle | How it is enforced |
|---|---|
| Determinism | Files processed in stable alphabetical / key order |
| No side-effects | NoOpSnapshotStore — no writes to R2 or local disk during base runs |
| Reproducibility | Per-source manifest JSON (SHA-256, R2 ETags, file paths) written before DB writes |
| Idempotency | Run twice → second run produces 0 new records |
| DB isolation | `sicurre.db` is deleted and recreated fresh before the first source runs |

**Replay procedure** (jury demo):
```bash
unset SICURRE_DATABASE_URL
make phishtank-ingest-base   # resets DB + ingests source 1
make file-ingest-base        # ingests source 2  (adds to existing DB)
# … further sources as they are implemented
```

---

## Makefile orchestration

| Target | Resets DB? | Script | Status |
|---|---|---|---|
| `phishtank-ingest-base` | **YES** (rm + alembic upgrade head) | `src/data_platform/base_ingest/api/phishtank/ingest.py` | ✅ Done |
| `file-ingest-base` | No | `src/data_platform/base_ingest/file/csv/ingest.py` | ✅ Done |
| `certfr-ingest-base` | No | `src/data_platform/base_ingest/scraping/certfr/ingest.py` | 🔜 Planned |
| `sap-ingest-base` | No | `src/data_platform/base_ingest/scraping/sap_labs/ingest.py` | 🔜 Planned |
| `db-ingest-base` | No | `src/data_platform/base_ingest/db/ingest.py` | 🔜 Planned |
| `bigdata-ingest-base` | No | `src/data_platform/base_ingest/bigdata/common_crawl/ingest.py` | 🔜 Planned |

> `phishtank-ingest-base` is the only target that resets the DB.
> All other targets assume an already-migrated `sicurre.db`.
> Running any single `*-ingest-base` standalone on an empty DB requires
> `uv run alembic upgrade head` first.

---

## Source 1 — PhishTank (API) ✅ Complete

**Run date**: 2026-04-19  
**Manifest**: `data/local/phishtank_base_ingest_manifest.json`  
**Script**: `src/data_platform/base_ingest/api/phishtank/ingest.py`  
**Make target**: `phishtank-ingest-base`

### What it does
Enumerates frozen CSV snapshots from two backends, deduplicates by SHA-256,
ingests French-targeted phishing entries into `data_raw_record` via
`PhishTankIngestionService`.  Snapshot writes are suppressed via
`NoOpSnapshotStore`.

### Input inventory (at manifest generation time)

**R2** (`raw-snapshots/phishtank/` — 3 objects):

| R2 Key | Size | SHA-256 (first 12) | Selected | Notes |
|---|---|---|---|---|
| `phishtank_20260417_1a62b0cc-….csv` | 338 KB | `ef7911a57d4d` | ✅ | No French matches |
| `phishtank_20260417_9bf7dde4-….csv` | 344 KB | `ae9eb15e0150` | ✅ | No French matches |
| `phishtank_20260418_6580783d-….csv` | 39 KB | `5fb18898566a` | ✅ | No French matches |

**Local** (`data/raw/api/phishtank/` — 14 CSV files selected from 15 discovered,
1 duplicate of an R2 snapshot suppressed):

| Filename | Rows | New records | Notes |
|---|---|---|---|
| `phishing-tank.csv` | 56,071 | **702** | Historical Kaggle export |
| `phishtank_20260418_71a9d649-….csv` | 57,245 | **103** | Partial overlap |
| `phishtank_20260418_866f4a3e-….csv` | 54 | **21** | Small test snapshot |
| `phishtank_20260418_cfd390db-….csv` | 57,236 | **1** | Nearly full overlap |
| `phishtank_20260418_d16fd7e4-….csv` | 68 | **2** | — |
| `phishtank_20260418_b3820dab-….csv` | 57,254 | 0 | All skipped (dup) |
| `phishtank_20260419_3df69d4d-….csv` | 57,198 | 0 | All skipped (dup) |
| (4 others) | — | 0 | No French matches |

### Results

| Metric | Value |
|---|---|
| Snapshots discovered | 17 (3 R2 + 14 local) |
| Duplicate snapshots suppressed | 3 |
| Unique snapshots processed | 14 |
| Total feed entries scanned | 365,317 |
| Non-French filtered | 361,096 |
| Dedup-skipped (already in DB) | 3,392 |
| **New records inserted** | **829** |
| Prior baseline (live API run) | 679 |
| **Delta** | **+150** |

---

## Source 2 — File (static datasets) ✅ Complete

**Run date**: 2026-04-19  
**Manifest**: `data/local/file_csv_base_ingest_manifest.json`  
**Script**: `src/data_platform/base_ingest/file/csv/ingest.py`  
**Make target**: `file-ingest-base`

### What it does
Enumerates all file assets under `data/raw/file/` by format (CSV → JSONL → TXT)
in stable alphabetical order within each group.  Writes a single SHA-256
manifest before any DB writes, then dispatches to per-format readers:

| Format | Reader | Location |
|---|---|---|
| `*.csv` | `ingest_csv_file()` | `csv_ingestion.py` (existing pipeline) |
| `*.jsonl` | `parse_jsonl()` | `jsonl_ingestion.py` (new) |
| `*.txt` | `parse_txt_emails()` | `txt_email_ingestion.py` (new) |

Unlike PhishTank there is **no R2 equivalent** — these are static datasets
stored permanently in the repo.  No snapshot writes are involved.

### Input inventory (`data/raw/file/`)

#### CSVs — 7 files (`data/raw/file/csv/**/*.csv`)

| File | Rows | New records | Schema | Language |
|---|---|---|---|---|
| `en/combined_final_clean.csv` | 113,094 | **111,166** | standard | EN |
| `en/cybersectony_legit_6606_20260301.csv` | 6,606 | **6,606** | standard | EN |
| `en/enron_hamspam_28191_20260301.csv` | 28,191 | **28,191** | standard | EN |
| `fr/french_spamham_1000_20260301.csv` | 1,000 | **1,000** | standard | FR |
| `fr/kaggle_multilingual_fr_4981_20260301.csv` | 4,981 | **4,981** | standard | FR |
| `kaggle_multilingual_spam.csv` | 5,574 | **5,157** | historical | Multi |
| `multilingual-spam-data/data-en-hi-de-fr.csv` | 5,574 | **5,157** | historical | Multi |

> ⚠️ **Duplicate content**: `kaggle_multilingual_spam.csv` and
> `multilingual-spam-data/data-en-hi-de-fr.csv` are **bit-for-bit identical**
> (SHA-256: `27e485e62a81`).  Two `DataRawObject` rows are created (different
> `external_ref`), but only 5,157 unique `DataRawRecord` rows each — within-file
> dedup via `record_key = sha256(text[:300])` catches 417 intra-file duplicates.
> Cross-file record overlap is tolerated by design (different `raw_object_id`).

#### TXT email files — 4 files (`data/raw/file/txt/*.txt`)

Real spam emails exported from inbox, parsed by `txt_email_ingestion.py`.
Record boundary: `   From:` (3-space indent).  Label: `spam` (hardcoded — all
emails in these files are spam by definition).

| File | Emails parsed | Inserted | Duplicates skipped |
|---|---|---|---|
| `Spam_1.txt` | 100 | **96** | 4 |
| `Spam_2.txt` | 27 | **26** | 1 |
| `Spam_3.txt` | 100 | **73** | 27 |
| `Spam_4.txt` | 100 | **85** | 15 |

> Duplicates = cross-email content collisions caught by `record_key = sha256(subject+body[:300])`.

#### Out-of-scope assets

| File | Format | Reason |
|---|---|---|
| `csv/french-spamham-detection-free/data.jsonl` | JSONL | Excluded per user decision — 1,000 FR entries already covered by `fr/french_spamham_1000_20260301.csv` |

### Results

| Metric | Value |
|---|---|
| Files discovered | 11 (7 CSV + 0 JSONL + 4 TXT) |
| **New records inserted** | **162,538** |
| Prior cumulative (after PhishTank) | 829 |
| **Cumulative total in sicurre.db** | **163,367** |

---

## Source 3 — CERT-FR (scraping) ✅ Complete

**Make target**: `certfr-ingest-base`  
**Script location**: `src/data_platform/base_ingest/scraping/certfr/ingest.py`  
**Manifest**: `data/local/certfr_base_ingest_manifest.json` ✅ written

### Input inventory (verified)

| Storage | Path / prefix | Objects | Format |
|---------|---------------|---------|--------|
| R2 | `raw-snapshots/cert-fr/` | **92** `.txt` | PDF-extracted or HTML-extracted text, one file per report |
| Local | `data/raw/scraping/cert_fr/cert-fr/` | **92** `.txt` | Identical to R2 (verified: sha-256 matches 100 %) |
| Local CSV | `data/raw/scraping/certfr/certfr_cti_reports_91_20260301.csv` | 91 rows | Structured metadata: `certfr_id, title, url, pub_date, text, is_phishing_related, …` |
| Local CSV | `data/raw/scraping/certfr/certfr_phishing_37_20260301.csv` | 37 rows | Phishing-relevant subset of the 91-row CSV (same schema) |

R2 filename pattern: `CERTFR-YYYY-{CTI|IOC}-NNN.{pdf|html}.txt`  
Split: 77 CTI reports + 15 IOC reports = 92 total.  
The 91-row CSV covers 91 of the 92 TXT files; `CERTFR-2026-CTI-002` is in R2/local only (newer, post-CSV).

### Deduplication strategy

1. Enumerate R2 sorted by key (canonical).  
2. Enumerate local sorted by filename.  
3. SHA-256 dedup — R2 wins on collision. Since all 92 files match byte-for-byte, all 92 are selected from R2; local provides 0 new files.  
4. DB idempotency guard: `external_ref = certfr_id` (e.g., `CERTFR-2019-CTI-001`) on `DataRawObject`.

### Label mapping

Load `certfr_cti_reports_91_20260301.csv` into a dict `{certfr_id → row}` before processing.

| Condition | Label |
|-----------|-------|
| `csv_meta["is_phishing_related"] == "True"` | `"phishing"` |
| `csv_meta["is_phishing_related"] == "False"` | `"legitimate"` |
| `certfr_id` not in CSV (e.g. `CERTFR-2026-CTI-002`) | `"legitimate"` (default) |

### Per-file record structure

Each TXT file → 1 `DataRawObject` + 1 `DataRawRecord`.

```
DataRawObject
  external_ref  = certfr_id          # "CERTFR-2019-CTI-001"
  source_format = "txt"
  content_hash  = sha256(file bytes)
  storage_uri   = r2://<bucket>/raw-snapshots/cert-fr/<filename>

DataRawRecord
  record_key    = sha256(text[:300])
  raw_content   = JSON {"text": ..., "label": ..., "source": "certfr",
                        "certfr_id": ..., "title": ..., "url": ...}
  detected_language = "fr"
```

### Expected output

| Metric | Value |
|--------|-------|
| Unique TXT files processed | 92 ✅ actual |
| New `data_raw_record` rows inserted | **92** |
| Cumulative `data_raw_record` after this source | **163,459** |

---

## Source 4 — SAP Labs Blog (scraping) ✅ Complete

**Make target**: `sap-ingest-base`  
**Script location**: `src/data_platform/base_ingest/scraping/sap_labs/ingest.py`  
**Manifest**: `data/local/sap_labs_base_ingest_manifest.json` ✅ written

### Input inventory (verified)

| Storage | Path / prefix | Objects | Emails per object | Unique IDs |
|---------|---------------|---------|-------------------|------------|
| R2 | `raw-snapshots/sap_labs/` | 3 JSON snapshots | 18 each | 18 total |
| Local | `data/raw/scraping/sap_labs/` | 4 JSON snapshots | 18 each | 18 total |
| Local fallback | `data/raw/scraping/sap_labs_fr_emails_18.json` | 1 JSON | 18 | 18 total |

All 8 files (3 R2 + 4 local + 1 fallback) contain **identical email IDs** (`sap-chatgpt-01…04`, `sap-train-01…14`) — confirmed by cross-inventory check.

R2 snapshot filenames: `sap_labs_scrape_YYYYMMDD_<uuid>.json`  
Local snapshot filenames: `sap_labs_scrape_20260418_<uuid>.json` (different UUIDs from R2)  
Fallback JSON: outer dict with keys `source, url, author, date, description, license, extracted, stats, emails`.

### Deduplication strategy

The `SapLabsIngestionService` (existing extractor) already handles all deduplication:
- `fetch_entries()` falls back to `sap_labs_fr_emails_18.json` (blog is blocked; scraper returns fallback).
- Record-level dedup via `_existing_record_keys()` (queries `data_raw_record` for previously seen keys).

**No R2 enumeration is needed at base-ingest time**: the canonical data comes from the fallback JSON, which contains the full de-duplicated set of 18 emails.

### Per-email record structure

Each email → 1 `DataRawRecord` (created by existing `SapLabsIngestionService._build_raw_records()`).

```
DataRawRecord
  record_key    = str(hash(subject))     # NOTE: Python hash — not cross-process stable;
                                         # acceptable for base-ingest since DB is fresh
  raw_content   = JSON {"subject": ..., "body": ..., "text": ..., "label": ...,
                        "source": "sap_labs_scrape", "brand_impersonated": ...,
                        "techniques": [...]}
  detected_language = "fr"
```

Labels in the dataset: `phishing` (12 emails) and `legitimate` (6 emails).

### Implementation pattern

Identical to PhishTank base ingest: inject `NoOpSnapshotStore` to suppress R2 writes, call `SapLabsIngestionService.run()` directly.

```python
service = SapLabsIngestionService(snapshot_store=NoOpSnapshotStore())
result = await service.run(session, trigger_mode="manual")
```

### Expected output

| Metric | Value |
|--------|-------|
| Emails in fallback JSON | 18 ✅ actual |
| New `data_raw_record` rows inserted | **18** |
| Cumulative `data_raw_record` after this source | **163,477** |

---

## Source 5 — External DB (historical) 🔜 Planned

**Make target** (to be added): `db-ingest-base`  
**Input**: `data/raw/db/external_threats.db` (seed + read)  
**Script location**: `src/data_platform/base_ingest/db/ingest.py`

---

## Source 6 — Common Crawl (bigdata) 🔜 Planned

**Make target** (to be added): `bigdata-ingest-base`  
**Input**: R2 `raw-snapshots/bigdata/common_crawl/` + local `data/raw/bigdata/`  
**Script location**: `src/data_platform/base_ingest/bigdata/common_crawl/ingest.py`

---

## Running total (after each source)

| After source | Cumulative records in `data_raw_record` |
|---|---|
| PhishTank ✅ | 829 |
| File (CSV + TXT) ✅ | **163,367** |
| CERT-FR ✅ | 163,459 |
| SAP Labs ✅ | **163,477** |
| External DB (est.) | TBD |
| Common Crawl (est.) | TBD |
