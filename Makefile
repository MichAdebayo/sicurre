.PHONY: help install test dev-api phishtank-ingest phishtank-cron phishtank-csv certfr-ingest certfr-cron sap-scrape csv-ingest db-seed db-ingest bigdata-crawl bigdata-ingest normalize normalize-dry normalize-common-crawl normalize-db-historical normalize-kaggle-fr normalize-kaggle-multilingual normalize-sap normalize-certfr adapt-phishing synthetic-data restructure-processed dataset-splits

NORMALIZE_ARGS ?=
ADAPT_ARGS ?=
SYNTH_ARGS ?=
RESTRUCTURE_ARGS ?=
SPLIT_ARGS ?=

help:
	@echo "Sicurre - Available Commands:"
	@echo "  make help               - Show this help message"
	@echo "  make install            - Install local python dependencies"
	@echo "  make test               - Run backend test suite"
	@echo "  make dev-api            - Start FastAPI development server"
	@echo "  make phishtank-ingest   - Run one-off PhishTank ingestion (Live CSV feed)"
	@echo "  make phishtank-cron     - Run recurring PhishTank ingestion (Cron target, HTTP feed)"
	@echo "  make phishtank-csv      - Run PhishTank ingestion from local CSV file (Fallback)"
	@echo "  make certfr-ingest      - Run one-off CERT-FR CTI ingestion (Historical full backfill)"
	@echo "  make certfr-cron        - Run recurring CERT-FR CTI ingestion (Cron target, RSS feed)"
	@echo "  make sap-scrape         - Run one-off SAP Labs Blog scraping ingestion"
	@echo "  make csv-ingest         - Run Universal CSV Dataset Ingestion (Machine Learning Sources)"
	@echo "  make db-seed            - Seed the standalone historical external database with CSV data"
	@echo "  make db-ingest          - Run Historical DB Ingestion from an external monolithic DB"
	@echo "  make bigdata-crawl      - Run Common Crawl extraction to Cloudflare R2"
	@echo "  make bigdata-ingest     - Manually ingest the latest Common Crawl snapshot into the local DB"
	@echo "  make normalize          - Normalize French raw records from the DB"
	@echo "  make normalize-dry      - Preview normalization output without DB writes"
	@echo "  make normalize-common-crawl      - Normalize Common Crawl records only"
	@echo "  make normalize-db-historical     - Normalize historical DB records only"
	@echo "  make normalize-kaggle-fr         - Normalize French SpamHam records only"
	@echo "  make normalize-kaggle-multilingual - Normalize French multilingual Kaggle records only"
	@echo "  make normalize-sap      - Normalize SAP Labs FR records only"
	@echo "  make normalize-certfr   - Normalize CERT-FR records only"
	@echo "  make adapt-phishing     - Generate culturally adapted French phishing data"
	@echo "  make synthetic-data     - Generate synthetic data from archetypes"
	@echo "  make restructure-processed - Build the processed 3-class export layout"
	@echo "  make dataset-splits     - Merge processed datasets into train/val/test splits"

install:
	uv sync

test:
	uv run pytest tests/

dev-api:
	uv run uvicorn src.data_platform.api.main:app --reload

phishtank-ingest:
	@echo "Starting one-off live ingestion..."
	uv run python src/data_platform/cron_schedulers/run_phishtank_ingestion.py --trigger manual

phishtank-cron:
	@echo "Starting scheduled live ingestion..."
	uv run python src/data_platform/cron_schedulers/run_phishtank_ingestion.py --trigger scheduled

phishtank-csv:
	@echo "Starting local CSV fallback ingestion..."
	uv run python src/data_platform/cron_schedulers/run_phishtank_ingestion.py --trigger manual --csv data/raw/api/phishtank/phishing-tank.csv

certfr-ingest:
	@echo "Starting full historical CERT-FR CTI backfill (HTML pagination)..."
	uv run python src/data_platform/cron_schedulers/run_certfr_cti.py --trigger manual --historical

certfr-cron:
	@echo "Starting scheduled CERT-FR CTI ingestion (RSS feed)..."
	uv run python src/data_platform/cron_schedulers/run_certfr_cti.py --trigger scheduled

csv-ingest:
	@echo "Starting Universal CSV dataset ingestion..."
	uv run python src/data_platform/cron_schedulers/run_csv_ingestion.py --dir data/raw/csv

sap-scrape:
	@echo "Starting SAP Labs Blog web scraping ingestion..."
	uv run python scripts/data_platform/sap_labs/ingestion/ingest_sap_labs_blog.py

db-seed:
	@echo "Seeding the isolated historical external DB..."
	uv run python scripts/data_platform/historical_db/setup/seed_external_db.py

db-ingest:
	@echo "Starting Database Ingestion from external monolithic DB..."
	uv run python scripts/data_platform/historical_db/ingestion/ingest_legacy_db_source.py

bigdata-crawl:
	@echo "Run the massive Common Crawl async extraction job to Cloudflare R2"
	uv run python scripts/data_platform/common_crawl/extraction/extract_common_crawl_snapshots.py

bigdata-ingest:
	@echo "Manually ingest the latest Common Crawl snapshot via BigQuery into sqlite"
	uv run python scripts/data_platform/common_crawl/ingestion/ingest_latest_common_crawl_snapshot.py

normalize:
	@echo "Running DB-backed French normalization pipeline..."
	uv run python scripts/data_platform/shared/normalization/run_normalization.py $(NORMALIZE_ARGS)

normalize-dry:
	@echo "Previewing DB-backed French normalization pipeline..."
	uv run python scripts/data_platform/shared/normalization/run_normalization.py --dry-run $(NORMALIZE_ARGS)

normalize-common-crawl:
	@echo "Normalizing Common Crawl records..."
	uv run python scripts/data_platform/shared/normalization/run_normalization.py --source common-crawl-bigdata $(NORMALIZE_ARGS)

normalize-db-historical:
	@echo "Normalizing historical DB records..."
	uv run python scripts/data_platform/shared/normalization/run_normalization.py --source database-historical $(NORMALIZE_ARGS)

normalize-kaggle-fr:
	@echo "Normalizing French SpamHam records..."
	uv run python scripts/data_platform/shared/normalization/run_normalization.py --source kaggle_french_spamham $(NORMALIZE_ARGS)

normalize-kaggle-multilingual:
	@echo "Normalizing French multilingual Kaggle records..."
	uv run python scripts/data_platform/shared/normalization/run_normalization.py --source kaggle_multilingual_spam $(NORMALIZE_ARGS)

normalize-sap:
	@echo "Normalizing SAP Labs FR records..."
	uv run python scripts/data_platform/shared/normalization/run_normalization.py --source sap-labs-blog $(NORMALIZE_ARGS)

normalize-certfr:
	@echo "Normalizing CERT-FR records..."
	uv run python scripts/data_platform/shared/normalization/run_normalization.py --source cert-fr-cti $(NORMALIZE_ARGS)

adapt-phishing:
	@echo "Generating culturally adapted French phishing emails..."
	uv run python scripts/data_platform/datasets/generation/generate_adapted_fr_phishing.py $(ADAPT_ARGS)

synthetic-data:
	@echo "Generating synthetic dataset rows from archetypes..."
	uv run python scripts/data_platform/datasets/generation/generate_synthetic_data.py $(SYNTH_ARGS)

restructure-processed:
	@echo "Building processed 3-class exports from curated sources..."
	uv run python scripts/data_platform/datasets/preparation/process_restructure_data.py $(RESTRUCTURE_ARGS)

dataset-splits:
	@echo "Building train/val/test splits from processed exports..."
	uv run python scripts/data_platform/datasets/preparation/merge_splits.py $(SPLIT_ARGS)
