.PHONY: help install test dev-api \
        phishtank-ingest-base phishtank-ingest phishtank-cron phishtank-csv \
        file-ingest-base file-ingest file-cron \
        scraping-ingest-base scraping-ingest scraping-cron \
        db-ingest-base db-ingest db-cron db-seed \
        bigdata-ingest-base \
        bigdata-crawl bigdata-ingest bigdata-cron bigdata-reviewed-promote \
        cron-orchestrate \
        normalize normalize-dry \
        generate-data dataset-build dataset-export \
        r2-freeze-proof

NORMALIZE_ARGS ?=
GENERATE_ARGS ?=
DATASET_ARGS ?=
EXPORT_ARGS ?=
BIGDATA_PROMOTION_ARGS ?=
CRON_ARGS ?=

help:
	@echo "Sicurre — Available Commands"
	@echo ""
	@echo "  Setup"
	@echo "  make install                   - Install local python dependencies"
	@echo "  make test                      - Run backend test suite"
	@echo "  make dev-api                   - Start FastAPI development server"
	@echo ""
	@echo "  Base Ingestion  (deterministic, frozen snapshots — used to build sicurre.db from scratch)"
	@echo "  make phishtank-ingest-base     - Reset DB, ingest all frozen PhishTank R2+local snapshots"
	@echo "  make file-ingest-base          - Ingest all local CSV datasets (no DB reset)"
	@echo "  make scraping-ingest-base      - Ingest frozen CERT-FR + SAP Labs snapshots (no DB reset)"
	@echo "  make db-ingest-base            - Seed external_threats.db (3-class, seed=42) + ingest into sicurre.db"
	@echo "  make bigdata-ingest-base       - Merge R2 + local CC CSVs into base parquet, then ingest into sicurre.db"
	@echo ""
	@echo "  Live Ingestion  (one-off manual backfill against live sources)"
	@echo "  make phishtank-ingest          - Live PhishTank ingestion (HTTP feed)"
	@echo "  make phishtank-csv             - PhishTank ingestion from local CSV fallback"
	@echo "  make file-ingest               - One-off CSV dataset ingestion"
	@echo "  make scraping-ingest           - Full historical CERT-FR backfill + SAP Labs scrape"
	@echo "  make db-ingest                 - Sync external_threats.db → sicurre.db only (no seeding; use after db-cron partial failure)"
	@echo ""
	@echo "  Cron  (scheduled, incremental — simulates production)"
	@echo "  make phishtank-cron            - Scheduled PhishTank ingestion"
	@echo "  make file-cron                 - Scheduled CSV ingestion"
	@echo "  make scraping-cron             - Scheduled CERT-FR scraping (capped index scan)"
	@echo "  make db-cron                   - Scheduled DB feed: append new rows to feeder DB + ingest delta"
	@echo "  make bigdata-cron              - Scheduled Common Crawl extract→ingest pipeline"
	@echo "  make cron-orchestrate          - Run full cron suite manually"
	@echo ""
	@echo "  Common Crawl"
	@echo "  make bigdata-crawl             - Run Common Crawl extraction to Cloudflare R2"
	@echo "  make bigdata-ingest            - Manually ingest latest Common Crawl snapshot"
	@echo "  make bigdata-reviewed-promote  - Promote reviewed Common Crawl exports into curated tables"
	@echo ""
	@echo "  R2 Freeze Proof  (upload all source files to R2 base/ and verify counts)"
	@echo "  make r2-freeze-proof           - Upload all sources to R2 base/, prove deterministic reproduction"
	@echo ""
	@echo "  Normalization"
	@echo "  make normalize                 - Normalize all raw records in sicurre.db"
	@echo "  make normalize-dry             - Preview normalization without DB writes"
	@echo ""
	@echo "  Dataset"
	@echo "  make generate-data             - Run canonical generation pipeline (adapted + CC lanes)"
	@echo "  make dataset-build             - Build DB-backed dataset from annotated normalized messages"
	@echo "  make dataset-export            - Serialize frozen dataset to CSV/JSONL for PyTorch"
	@echo ""
	@echo "  Dev"
	@echo "  make db-seed                   - Manually seed external_threats.db (dev utility, supports --append-n)"

install:
	uv sync

test:
	uv run pytest tests/

dev-api:
	uv run uvicorn src.data_platform.api.main:app --reload

# ── Base Ingestion ─────────────────────────────────────────────────────────────

phishtank-ingest-base:
	@echo "Resetting sicurre.db and running deterministic PhishTank base ingestion (R2 + local)..."
	rm -f data/local/sicurre.db
	uv run alembic upgrade head
	uv run python src/data_platform/base_ingest/api/phishtank/ingest.py

file-ingest-base:
	@echo "Running deterministic CSV file base ingestion (no DB reset)..."
	uv run python src/data_platform/base_ingest/file/csv/ingest.py

scraping-ingest-base:
	@echo "Running deterministic scraping base ingestion: CERT-FR then SAP Labs (no DB reset)..."
	uv run python src/data_platform/base_ingest/scraping/certfr/ingest.py
	uv run python src/data_platform/base_ingest/scraping/sap_labs/ingest.py

db-ingest-base:
	@echo "Seeding external_threats.db (3-class, seed=42) then ingesting into sicurre.db (deterministic)..."
	unset SICURRE_DATABASE_URL && uv run python src/data_platform/base_ingest/db/ingest.py

# ── Live Ingestion ─────────────────────────────────────────────────────────────

phishtank-ingest:
	@echo "Starting one-off live PhishTank ingestion..."
	uv run python src/data_platform/cli/ingest/api/phishtank.py --trigger manual

phishtank-csv:
	@echo "Starting PhishTank ingestion from local CSV fallback..."
	uv run python src/data_platform/cli/ingest/api/phishtank.py --trigger manual --csv data/raw/api/phishtank/phishing-tank.csv

file-ingest:
	@echo "Starting one-off CSV dataset ingestion..."
	uv run python src/data_platform/cli/ingest/file/csv_ingestion.py --dir data/raw/file/csv

scraping-ingest:
	@echo "Starting full historical CERT-FR backfill then SAP Labs scrape..."
	uv run python src/data_platform/cli/ingest/scraping/certfr.py --trigger manual --historical
	uv run python src/data_platform/cli/ingest/scraping/sap_labs.py

db-ingest:
	@echo "Starting full backfill: sync all external_threats.db rows into sicurre.db..."
	uv run python src/data_platform/cli/ingest/database/legacy_db.py

# ── Cron ──────────────────────────────────────────────────────────────────────

phishtank-cron:
	@echo "Running scheduled PhishTank ingestion..."
	uv run python src/data_platform/cli/ingest/api/phishtank.py --trigger scheduled

file-cron:
	@echo "Running scheduled CSV ingestion..."
	uv run python src/data_platform/cron_schedulers/file/run_csv_ingestion.py

scraping-cron:
	@echo "Running scheduled CERT-FR scraping (capped index scan)..."
	uv run python src/data_platform/cron_schedulers/scraping/run_certfr_cti.py

db-cron:
	@echo "Running scheduled DB feed: append new rows to feeder DB + ingest delta into sicurre.db..."
	uv run python src/data_platform/cron_schedulers/database/run_database_historical_feed.py

bigdata-ingest-base:
	@echo "Step 1/2 — Building merged Common Crawl base parquet (R2 + legacy CSVs, dedup by content_hash)..."
	unset SICURRE_DATABASE_URL && uv run python scripts/data_platform/common_crawl/ingestion/build_base_merged_snapshot.py
	@echo "Step 2/2 — Ingesting base parquet into sicurre.db via LocalCommonCrawlClient..."
	unset SICURRE_DATABASE_URL && uv run python src/data_platform/base_ingest/bigdata/common_crawl/ingest.py

bigdata-crawl:
	@echo "Running Common Crawl extraction to Cloudflare R2..."
	uv run python src/data_platform/cli/bigdata/common_crawl_extract.py

bigdata-ingest:
	@echo "Manually ingesting latest Common Crawl snapshot..."
	uv run python src/data_platform/cli/bigdata/common_crawl_ingest.py

bigdata-cron:
	@echo "Running scheduled Common Crawl extract→ingest pipeline..."
	uv run python src/data_platform/cron_schedulers/bigdata/run_common_crawl_pipeline.py

bigdata-reviewed-promote:
	@echo "Promoting reviewed Common Crawl exports into curated tables..."
	uv run python src/data_platform/cli/bigdata/common_crawl_reviewed_promotion.py $(BIGDATA_PROMOTION_ARGS)

cron-orchestrate:
	@echo "Running full cron suite manually..."
	uv run python src/data_platform/cli/maintenance/cron_orchestrator.py $(CRON_ARGS)

# ── Normalization ─────────────────────────────────────────────────────────────

normalize:
	@echo "Normalizing all raw records in sicurre.db..."
	uv run python src/data_platform/cli/normalize/messages.py $(NORMALIZE_ARGS)

normalize-dry:
	@echo "Previewing normalization (no DB writes)..."
	uv run python src/data_platform/cli/normalize/messages.py --dry-run $(NORMALIZE_ARGS)

# ── Dataset ───────────────────────────────────────────────────────────────────

generate-data:
	@echo "Running canonical generation pipeline (adapted + CC lanes)..."
	uv run python src/data_platform/cli/datasets/generate.py $(GENERATE_ARGS)

dataset-build:
	@echo "Building DB-backed dataset from annotated normalized messages..."
	uv run python src/data_platform/cli/datasets/build.py $(DATASET_ARGS)

dataset-export:
	@echo "Serializing frozen dataset to CSV/JSONL for PyTorch..."
	uv run python src/data_platform/cli/datasets/export.py $(EXPORT_ARGS)

# ── Dev ───────────────────────────────────────────────────────────────────────

db-seed:
	@echo "Manually seeding external_threats.db (dev utility)..."
	uv run python src/data_platform/cli/dev/seed_external_db.py

# ── R2 Freeze Proof ───────────────────────────────────────────────────────────

r2-freeze-proof:
	@echo "Uploading all source files to R2 base/ prefixes and verifying counts..."
	@echo "sicurre.db BEFORE: $$(sqlite3 data/local/sicurre.db 'SELECT COUNT(*) FROM data_raw_record') rows"
	unset SICURRE_DATABASE_URL && uv run python scripts/data_platform/shared/r2_freeze_proof/run_all.py
