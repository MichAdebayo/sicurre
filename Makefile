.PHONY: help install test dev-api phishtank-ingest phishtank-cron phishtank-csv certfr-ingest certfr-cron sap-scrape csv-ingest db-seed db-ingest bigdata-crawl bigdata-ingest bigdata-reviewed-promote normalize normalize-dry normalize-common-crawl normalize-db-historical normalize-kaggle-fr normalize-kaggle-multilingual normalize-sap normalize-certfr generate-data restructure-processed dataset-splits dataset-build

NORMALIZE_ARGS ?=
GENERATE_ARGS ?=
DATASET_ARGS ?=
EXPORT_ARGS ?=
BIGDATA_PROMOTION_ARGS ?=

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
	@echo "  make certfr-cron        - Run recurring CERT-FR CTI ingestion (Cron target, capped index scan)"
	@echo "  make sap-scrape         - Run one-off SAP Labs Blog scraping ingestion"
	@echo "  make csv-ingest         - Run Universal CSV Dataset Ingestion (Machine Learning Sources)"
	@echo "  make db-seed            - Seed the standalone historical external database with CSV data"
	@echo "  make db-ingest          - Run Historical DB Ingestion from an external monolithic DB"
	@echo "  make bigdata-crawl      - Run Common Crawl extraction to Cloudflare R2"
	@echo "  make bigdata-ingest     - Manually ingest the latest Common Crawl snapshot into the local DB"
	@echo "  make bigdata-reviewed-promote - Promote reviewed Common Crawl exports into curated tables"
	@echo "  make normalize          - Normalize French raw records from the DB"
	@echo "  make normalize-dry      - Preview normalization output without DB writes"
	@echo "  make normalize-common-crawl      - Normalize Common Crawl records only"
	@echo "  make normalize-db-historical     - Normalize historical DB records only"
	@echo "  make normalize-kaggle-fr         - Normalize French SpamHam records only"
	@echo "  make normalize-kaggle-multilingual - Normalize French multilingual Kaggle records only"
	@echo "  make normalize-sap      - Normalize SAP Labs FR records only"
	@echo "  make normalize-certfr   - Normalize CERT-FR records only"
	@echo "  make generate-data      - Run the canonical in-memory generation pipeline and persist directly to DB"
	@echo "  make dataset-build      - Build a DB-backed dataset from annotated normalized messages"
	@echo "  make dataset-export     - Serialize frozen SQL dataset out to CSV/JSONL for PyTorch"

install:
	uv sync

test:
	uv run pytest tests/

dev-api:
	uv run uvicorn src.data_platform.api.main:app --reload

phishtank-ingest:
	@echo "Starting one-off live ingestion..."
	uv run python src/data_platform/cli/ingest/api/phishtank.py --trigger manual

phishtank-cron:
	@echo "Starting scheduled live ingestion..."
	uv run python src/data_platform/cli/ingest/api/phishtank.py --trigger scheduled

phishtank-csv:
	@echo "Starting local CSV fallback ingestion..."
	uv run python src/data_platform/cli/ingest/api/phishtank.py --trigger manual --csv data/raw/api/phishtank/phishing-tank.csv

certfr-ingest:
	@echo "Starting full historical CERT-FR CTI backfill (HTML pagination)..."
	uv run python src/data_platform/cli/ingest/scraping/certfr.py --trigger manual --historical

certfr-cron:
	@echo "Starting scheduled CERT-FR CTI ingestion (capped paginated index scan)..."
	uv run python src/data_platform/cli/ingest/scraping/certfr.py --trigger scheduled

csv-ingest:
	@echo "Starting Universal CSV dataset ingestion..."
	uv run python src/data_platform/cli/ingest/file/csv_ingestion.py --dir data/raw/csv

sap-scrape:
	@echo "Starting SAP Labs Blog web scraping ingestion..."
	uv run python src/data_platform/cli/ingest/scraping/sap_labs.py

db-seed:
	@echo "Seeding the isolated historical external DB..."
	uv run python src/data_platform/cli/dev/seed_external_db.py

db-ingest:
	@echo "Starting Database Ingestion from external monolithic DB..."
	uv run python src/data_platform/cli/ingest/database/legacy_db.py

bigdata-crawl:
	@echo "Run the massive Common Crawl async extraction job to Cloudflare R2"
	uv run python src/data_platform/cli/bigdata/common_crawl_extract.py

bigdata-ingest:
	@echo "Manually ingest the latest Common Crawl snapshot via BigQuery into sqlite"
	uv run python src/data_platform/cli/bigdata/common_crawl_ingest.py

bigdata-reviewed-promote:
	@echo "Promoting reviewed Common Crawl exports into curated tables..."
	uv run python src/data_platform/cli/bigdata/common_crawl_reviewed_promotion.py $(BIGDATA_PROMOTION_ARGS)

normalize:
	@echo "Running DB-backed French normalization pipeline..."
	uv run python src/data_platform/cli/normalize/messages.py $(NORMALIZE_ARGS)

normalize-dry:
	@echo "Previewing DB-backed French normalization pipeline..."
	uv run python src/data_platform/cli/normalize/messages.py --dry-run $(NORMALIZE_ARGS)

normalize-common-crawl:
	@echo "Normalizing Common Crawl records..."
	uv run python src/data_platform/cli/normalize/messages.py --source common-crawl-bigdata $(NORMALIZE_ARGS)

normalize-db-historical:
	@echo "Normalizing historical DB records..."
	uv run python src/data_platform/cli/normalize/messages.py --source database-historical $(NORMALIZE_ARGS)

normalize-kaggle-fr:
	@echo "Normalizing French SpamHam records..."
	uv run python src/data_platform/cli/normalize/messages.py --source kaggle_french_spamham $(NORMALIZE_ARGS)

normalize-kaggle-multilingual:
	@echo "Normalizing French multilingual Kaggle records..."
	uv run python src/data_platform/cli/normalize/messages.py --source kaggle_multilingual_spam $(NORMALIZE_ARGS)

normalize-sap:
	@echo "Normalizing SAP Labs FR records..."
	uv run python src/data_platform/cli/normalize/messages.py --source sap-labs-blog $(NORMALIZE_ARGS)

normalize-certfr:
	@echo "Normalizing CERT-FR records..."
	uv run python src/data_platform/cli/normalize/messages.py --source cert-fr-cti $(NORMALIZE_ARGS)

generate-data:
	@echo "Running the canonical in-memory generation pipeline..."
	uv run python src/data_platform/cli/datasets/generate.py $(GENERATE_ARGS)

dataset-build:
	@echo "Build a DB-backed dataset from annotated normalized messages"
	uv run python src/data_platform/cli/datasets/build.py $(DATASET_ARGS)

dataset-export:
	@echo "Serialize frozen SQL dataset out to CSV/JSONL for ML training"
	uv run python src/data_platform/cli/datasets/export.py $(EXPORT_ARGS)
