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
│       └── crowdsourced/               #   User-forwarded phishing emails (anonymized)
│
├── processed/                          # Cleaned, normalized, single-source outputs
│   ├── synthetic/                      #   LLM-generated French phishing emails
│   ├── adapted/                        #   English→French culturally adapted emails
│   └── legitimate/                     #   Legitimate French emails (ham)
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
│   ├── 03_bigquery_extraction.ipynb
│   └── 04_common_crawl_extraction.ipynb
├── api/                                # Mirrors data/raw/api/
├── scraping/                           # Mirrors data/raw/scraping/
├── csv/                                # Mirrors data/raw/csv/
├── db/                                 # Mirrors data/raw/db/
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
