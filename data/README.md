# Data Directory — Sicurre

## Structure

Organized by **C1 source type** — each folder maps directly to a Simplon competency requirement.

```
data/
├── raw/                                # Untouched data from each source (never modify in-place)
│   │
│   ├── bigdata/                        # C1: Système big data
│   │   ├── bigquery/                   #   Google BigQuery — English phishing emails (120K source)
│   │   └── common_crawl/              #   Common Crawl — FR bank/gov pages (hyper-filtered)
│   │
│   ├── api/                            # C1: API REST
│   │   └── phishtank/                  #   PhishTank API — phishing URLs (.fr filtered)
│   │
│   ├── scraping/                       # C1: Scraping
│   │   └── certfr/                     #   CERT-FR — CTI advisories, PDFs, extracted IOCs
│   │
│   ├── csv/                            # C1: Fichier (CSV/JSON datasets)
│   │                                   #   Kinoux FR Spam/Ham 2K, Kaggle Multilingual, etc.
│   │
│   └── db/                             # C1: Base de données
│       ├── adapted_fr_phishing.csv     #   EN→FR cultural adaptation (notebook 10)
│       ├── synthetic_fr_emails.csv     #   Synthetic French generation (notebook 11)
│       └── sicurre_dev.db              #   SQLite dev DB seeded from above (notebook 09)
│
├── processed/                          # Cleaned, normalized, single-source outputs
│   ├── adapted/                        #   EN→FR adapted phishing (2,145 cleaned, NB12)
│   │   └── adapted_clean_2145_<date>.csv
│   ├── synthetic/                      #   Synthetic FR phishing (1,747 cleaned, NB12)
│   │   └── synthetic_clean_1747_<date>.csv
│   └── legitimate/                     #   All legitimate emails (7,461 cleaned, NB12)
│       └── legitimate_clean_7461_<date>.csv
│
├── final/                              # Aggregated, balanced, RGPD-compliant, ready for training
│   ├── train/                          #   70% split
│   ├── val/                            #   15% split
│   └── test/                           #   15% split (held-out, never touched during training)
│
└── models/                             # Fine-tuned model artifacts
    └── camembertv2-phishing-fr/        #   ONNX + tokenizer + config
```

### Corresponding notebooks (git-tracked)

```
notebooks/
├── bigdata/                            # Mirrors data/raw/bigdata/
│   ├── 03_bigquery_extraction.ipynb    #   BigQuery: HF phishing dataset → 4,597 EN emails
│   └── 04_common_crawl_extraction.ipynb #  CC Index: FR bank/gov pages (28 usable)
├── api/                                # Mirrors data/raw/api/
│   └── 05_phishtank_extraction.ipynb   #   PhishTank JSON feed → FR phishing URLs
├── scraping/                           # Mirrors data/raw/scraping/
│   └── 06_certfr_extraction.ipynb      #   CERT-FR CTI + IOC pages → FR threat intel
├── csv/                                # Mirrors data/raw/csv/
│   └── 08_csv_sources.ipynb            #   HF + Kaggle CSV/Parquet → normalized ham/spam
├── db/                                 # Mirrors data/raw/db/
│   ├── 09_db_extraction.ipynb          #   SQLite dev DB → seed from adapted+synthetic → SQL queries
│   ├── 10_en_fr_cultural_adaptation.ipynb #  EN→FR pattern-based adaptation (Task 1.8)
│   └── 11_synthetic_fr_phishing.ipynb  #   Synthetic French phishing+legit generation (Task 1.3)
├── processing/                         # Data cleaning & normalization
│   └── 12_data_cleaning_normalization.ipynb # Raw→processed pipeline (PII anon, dedup, routing)
└── ml/                                 # Model training & evaluation
    └── 07_camembertv2_finetuning.ipynb
```

## Conventions

- **raw/** is immutable — scripts read from here, never write back.
- **processed/** holds single-source cleaned outputs.
- **final/** holds the merged, deduplicated, balanced dataset used for training.
- All CSVs use UTF-8 encoding with columns: `text`, `label`, `source`, `language`, `timestamp`.
- Labels: `0` = legitimate (ham), `1` = phishing.
- PII is anonymized before any data leaves `raw/` → `processed/`.

## RGPD

- No raw email bodies with PII are committed to git.
- `data/` is gitignored. Only scripts and notebooks that produce the data are versioned.
- See `docs/architecture/privacy-rgpd.md` for full compliance documentation.
