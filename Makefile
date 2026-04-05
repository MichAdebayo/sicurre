.PHONY: help install test dev-api phishtank-ingest phishtank-cron phishtank-csv

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

install:
	uv sync

test:
	uv run pytest tests/

dev-api:
	uv run uvicorn src.data_platform.api.main:app --reload

phishtank-ingest:
	@echo "Starting one-off live ingestion..."
	uv run python scripts/data_platform/run_phishtank_ingestion.py --trigger manual

phishtank-cron:
	@echo "Starting scheduled live ingestion..."
	uv run python scripts/data_platform/run_phishtank_ingestion.py --trigger scheduled

phishtank-csv:
	@echo "Starting local CSV fallback ingestion..."
	uv run python scripts/data_platform/run_phishtank_ingestion.py --trigger manual --csv data/raw/api/phishtank/phishing-tank.csv

certfr-ingest:
	@echo "Starting full historical CERT-FR CTI backfill (HTML pagination)..."
	uv run python scripts/data_platform/run_certfr_cti.py --trigger manual --historical

certfr-cron:
	@echo "Starting scheduled CERT-FR CTI ingestion (RSS feed)..."
	uv run python scripts/data_platform/run_certfr_cti.py --trigger scheduled

csv-ingest:
	@echo "Starting Universal CSV dataset ingestion..."
	uv run python scripts/data_platform/csv_ingestion.py --dir data/raw/csv

sap-scrape:
	@echo "Starting SAP Labs Blog web scraping ingestion..."
	uv run python scripts/data_platform/run_sap_labs_scraper.py
