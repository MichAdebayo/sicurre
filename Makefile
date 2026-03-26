.PHONY: help install test dev-api phishtank-ingest phishtank-cron phishtank-csv

help:
	@echo "Sicurre - Available Commands:"
	@echo "  make install            - Install local python dependencies"
	@echo "  make test               - Run backend test suite"
	@echo "  make dev-api            - Start FastAPI development server"
	@echo "  make phishtank-ingest   - Run one-off PhishTank ingestion (Live CSV feed)"
	@echo "  make phishtank-cron     - Run recurring PhishTank ingestion (Cron target, HTTP feed)"
	@echo "  make phishtank-csv      - Run PhishTank ingestion from local CSV file (Fallback)"

install:
	uv sync

test:
	uv run pytest backend/tests/

dev-api:
	cd backend && uv run uvicorn src.sicurre_api.main:app --reload

phishtank-ingest:
	@echo "Starting one-off live ingestion..."
	cd backend && uv run --group backend python scripts/run_phishtank_ingestion.py --trigger manual

phishtank-cron:
	@echo "Starting scheduled live ingestion..."
	cd backend && uv run --group backend python scripts/run_phishtank_ingestion.py --trigger scheduled

phishtank-csv:
	@echo "Starting local CSV fallback ingestion..."
	cd backend && uv run --group backend python scripts/run_phishtank_ingestion.py --trigger manual --csv ../data/raw/api/phishtank/phishing-tank.csv
