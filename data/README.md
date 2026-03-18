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
│       ├── adapted_fr_phishing.csv     #   EN→FR cultural adaptation (script-based workflow)
│       ├── synthetic_fr_emails.csv     #   Synthetic French generation (script-based workflow)
│       └── sicurre_dev.db              #   SQLite dev DB seeded from the extracted datasets
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

### Active notebooks and migrated script replacements

```
notebooks/
└── ml/                                 # Model training & evaluation
    └── 07_camembertv2_finetuning.ipynb #   The only notebook still kept in the active workflow
```

### Migrated script replacements

- `scripts/run_common_crawl.py` replaces the deleted Common Crawl extraction notebook.
- `scripts/generate_synthetic_data.py` replaces the deleted synthetic phishing generation notebook.
- `scripts/process_restructure_data.py` and shared backend preprocessing replace the deleted cleaning notebook.
- `scripts/generate_adapted_fr_phishing.py` replaces the deleted cultural adaptation notebook.
- Historical notes for all retired notebooks live in `docs/architecture/notebook-archive.md`.

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
