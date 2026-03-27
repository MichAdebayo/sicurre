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
	@echo "  make csv-ingest         - Run Universal CSV Dataset Ingestion (Machine Learning Sources)"

install:
	uv sync

test:
	uv run pytest backend/tests/

dev-api:
	cd backend && uv run uvicorn src.data_platform.api.main:app --reload

phishtank-ingest:
	@echo "Starting one-off live ingestion..."
	cd backend && uv run --group backend python scripts/run_phishtank_ingestion.py --trigger manual

phishtank-cron:
	@echo "Starting scheduled live ingestion..."
	cd backend && uv run --group backend python scripts/run_phishtank_ingestion.py --trigger scheduled

phishtank-csv:
	@echo "Starting local CSV fallback ingestion..."
	cd backend && uv run --group backend python scripts/run_phishtank_ingestion.py --trigger manual --csv ../data/raw/api/phishtank/phishing-tank.csv

certfr-ingest:
	@echo "Starting full historical CERT-FR CTI backfill (HTML pagination)..."
	cd backend && uv run --group backend python scripts/run_certfr_cti.py --trigger manual --historical

certfr-cron:
	@echo "Starting scheduled CERT-FR CTI ingestion (RSS feed)..."
	cd backend && uv run --group backend python scripts/run_certfr_cti.py --trigger scheduled

csv-ingest:
	@echo "Starting Universal CSV dataset ingestion..."
	cd backend && uv run --group backend python scripts/csv_ingestion.py --dir ../data/raw/csv
