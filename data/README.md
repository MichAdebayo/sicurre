# Data Directory — Sicurre

## Structure

```
data/
├── raw/                        # Untouched data from each source (never modify in-place)
│   ├── phishtank/              # PhishTank API JSON/CSV exports (.fr filtered)
│   ├── certfr/                 # CERT-FR CTI PDFs + extracted IOCs (JSON)
│   ├── bigquery/               # BigQuery exports — English phishing emails (200K source)
│   ├── csv_sources/            # Downloaded datasets (Kinoux FR Spam/Ham 2K, Kaggle Multilingual)
│   └── crowdsourced/           # User-forwarded phishing emails (anonymized)
│
├── processed/                  # Cleaned, normalized, single-source outputs
│   ├── synthetic/              # LLM-generated French phishing emails
│   ├── adapted/                # English→French culturally adapted emails (from BigQuery source)
│   └── legitimate/             # Legitimate French emails (ham) — mailing lists, donations
│
├── final/                      # Aggregated, balanced, RGPD-compliant, ready for training
│   ├── train/                  # 70% split
│   ├── val/                    # 15% split
│   └── test/                   # 15% split (held-out, never touched during training)
│
└── models/                     # Fine-tuned model artifacts
    └── camembertv2-phishing-fr/  # ONNX + tokenizer + config
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
