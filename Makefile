.PHONY: help install test dev-api \
        ingest-all-base \
        phishtank-ingest-base \
        file-ingest-base \
        scraping-ingest-base \
        db-ingest-base \
        bigdata-ingest-base \
        phishtank-cron file-cron scraping-cron db-cron bigdata-cron \
        cron-orchestrate ingest-all-cron \
        bigdata-crawl bigdata-ingest bigdata-reviewed-promote \
        normalize normalize-dry \
        annotate \
        generate-data dataset-build dataset-export \
        pipeline-push demo-v1 demo-v2 \
        poc db-seed r2-freeze-proof

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
	@echo "  make ingest-all-base           - Wipe DB and run ALL base ingestion steps in order"
	@echo "  make phishtank-ingest-base     - Reset DB, ingest all frozen PhishTank R2+local snapshots"
	@echo "  make file-ingest-base          - Ingest all local CSV datasets (no DB reset)"
	@echo "  make scraping-ingest-base      - Ingest frozen CERT-FR + SAP Labs snapshots (no DB reset)"
	@echo "  make db-ingest-base            - Seed external_threats.db (3-class, seed=42) + ingest into sicurre.db"
	@echo "  make bigdata-ingest-base       - Merge R2 + local CC CSVs into base parquet, then ingest into sicurre.db"
	@echo ""
	@echo "  Cron  (scheduled, incremental — simulates production)"
	@echo "  make phishtank-cron            - Scheduled PhishTank ingestion"
	@echo "  make file-cron                 - Scheduled CSV ingestion"
	@echo "  make scraping-cron             - Scheduled CERT-FR scraping (capped index scan)"
	@echo "  make db-cron                   - Scheduled DB feed: ingest delta from external_threats.db"
	@echo "  make bigdata-cron              - Scheduled Common Crawl extract→ingest pipeline"
	@echo "  make ingest-all-cron           - Run full cron ingestion suite"
	@echo ""
	@echo "  Pipeline & Demos"
	@echo "  make pipeline-push             - Push raw data through normalize → annotate → dataset-build"
	@echo "  make demo-v1                   - Full demo: base ingestion + pipeline push (dataset v1)"
	@echo "  make demo-v2                   - Full demo: generate delta + cron ingestion + pipeline push (dataset v2)"
	@echo ""
	@echo "  Dataset"
	@echo "  make generate-data             - Run canonical generation pipeline (adapted + CC lanes)"
	@echo "  make dataset-build             - Build DB-backed dataset from annotated normalized messages"
	@echo "  make dataset-export            - Serialize frozen dataset to CSV/JSONL for PyTorch"
	@echo ""
	@echo "  POC"
	@echo "  make poc                       - Launch Streamlit POC dashboard"
	@echo ""
	@echo "  Dev"
	@echo "  make db-seed                   - Manually seed external_threats.db (dev utility)"

install:
	uv sync

test:
	uv run pytest tests/

dev-api:
	uv run uvicorn src.data_platform.api.main:app --reload

# ── Base Ingestion ─────────────────────────────────────────────────────────────

ingest-all-base: phishtank-ingest-base file-ingest-base scraping-ingest-base db-ingest-base bigdata-ingest-base
	@echo ""
	@echo "============================================================================"
	@echo "  ALL BASE INGESTION COMPLETE"
	@echo "============================================================================"
	@echo "  Total rows: $$(sqlite3 data/local/sicurre.db 'SELECT COUNT(*) FROM data_raw_record')"
	@echo "  Target    : 192,037"
	@echo "============================================================================"

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

# ── Cron ──────────────────────────────────────────────────────────────────────

phishtank-cron:
	@echo "Running scheduled PhishTank ingestion..."
	uv run python src/data_platform/cron_schedulers/api/run_phishtank_ingestion.py

file-cron:
	@echo "Running scheduled CSV ingestion..."
	uv run python src/data_platform/cron_schedulers/file/run_csv_ingestion.py

scraping-cron:
	@echo "Running scheduled CERT-FR scraping (capped index scan)..."
	uv run python src/data_platform/cron_schedulers/scraping/run_certfr_cti.py

db-cron:
	@echo "Running scheduled DB feed: append new rows to feeder DB + ingest delta into sicurre.db..."
	uv run python src/data_platform/cron_schedulers/database/run_sql_ingestion.py

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
	uv run python src/data_platform/cron_schedulers/bigdata/run_incremental_cc.py

bigdata-reviewed-promote:
	@echo "Promoting reviewed Common Crawl exports into curated tables..."
	uv run python src/data_platform/cli/bigdata/common_crawl_reviewed_promotion.py $(BIGDATA_PROMOTION_ARGS)

cron-orchestrate:
	@echo "Running full cron suite manually..."
	uv run python src/data_platform/cli/maintenance/cron_orchestrator.py $(CRON_ARGS)

ingest-all-cron: cron-orchestrate
	@echo "All cron ingestion tasks completed."

# ── Normalization ─────────────────────────────────────────────────────────────

normalize:
	@echo "Normalizing all raw records in sicurre.db..."
	uv run python src/data_platform/cli/normalize/messages.py $(NORMALIZE_ARGS)

normalize-dry:
	@echo "Previewing normalization (no DB writes)..."
	uv run python src/data_platform/cli/normalize/messages.py --dry-run $(NORMALIZE_ARGS)

# ── Annotation ────────────────────────────────────────────────────────────────

annotate:
	@echo "Backfilling missing annotations on normalized messages..."
	uv run python src/data_platform/cli/maintenance/annotation_backfill.py

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

# ── Pipeline & Demos ──────────────────────────────────────────────────────────

pipeline-push: normalize annotate dataset-build
	@echo "Data pushed through normalization, annotation, and dataset builder."

demo-v1: ingest-all-base pipeline-push
	@echo "Demo V1 Dataset Generated"

demo-v2:
	@echo "Simulating time passage: Generating 50 new external threat records..."
	uv run python src/data_platform/cli/generate_sql_delta.py -n 50
	@echo "Running cron..."
	$(MAKE) ingest-all-cron
	@echo "Pushing new data through pipeline..."
	$(MAKE) pipeline-push
	@echo "Demo V2 Dataset Generated"

# ── POC ───────────────────────────────────────────────────────────────────────

poc-seed:
	@echo "Seeding POC users (admin + demo)..."
	uv run python src/poc/seed_users.py

poc: poc-seed
	@echo "Starting Sicurre POC Streamlit Dashboard..."
	uv run streamlit run src/poc/app.py --server.port 8501

# ── Dev ───────────────────────────────────────────────────────────────────────

db-seed:
	@echo "Manually seeding external_threats.db (dev utility)..."
	uv run python src/data_platform/cli/dev/seed_external_db.py

# ── R2 Freeze Proof ───────────────────────────────────────────────────────────

r2-freeze-proof:
	@echo "Uploading all source files to R2 base/ prefixes and verifying counts..."
	@echo "sicurre.db BEFORE: $$(sqlite3 data/local/sicurre.db 'SELECT COUNT(*) FROM data_raw_record') rows"
	unset SICURRE_DATABASE_URL && uv run python scripts/data_platform/shared/r2_freeze_proof/run_all.py
