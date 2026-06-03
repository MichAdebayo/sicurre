.PHONY: help install test dev-api test-inference \
        ingest-all-base \
        phishtank-ingest-base \
        file-ingest-base \
        scraping-ingest-base \
        db-ingest-base \
        bigdata-ingest-base \
        phishtank-cron file-cron scraping-cron db-cron bigdata-cron \
        phishtank-cron-reserved file-cron-reserved scraping-cron-reserved \
        db-cron-reserved bigdata-cron-reserved \
        cron-orchestrate ingest-all-cron \
        bigdata-crawl bigdata-ingest bigdata-reviewed-promote \
        normalize normalize-dry \
        annotate \
        generate-data dataset-build dataset-export \
        seed-frozen-dataset \
        pipeline-push demo-v1 demo-v2 \
        poc db-seed r2-freeze-proof

NORMALIZE_ARGS ?=
GENERATE_ARGS ?=
DATASET_ARGS ?=
DATASET_NAME ?= sicurre_training
DATASET_TAG_PREFIX ?= base
DATASET_VERSION_TAG := $(DATASET_TAG_PREFIX)-$(shell date -u +%Y%m%d-%H%M%S)
DATASET_TARGET_USAGE ?= training
DATASET_STATUS ?= frozen
EXPORT_ARGS ?=
BIGDATA_PROMOTION_ARGS ?=
CRON_ARGS ?=

help:
	@echo "Sicurre — Available Commands"
	@echo ""
	@echo "  Setup"
	@echo "  make install                   - Install local python dependencies"
	@echo "  make test                      - Run backend test suite"
	@echo "  make test-inference            - Smoke-test the inference API (localhost:8000)"
	@echo "  make dev-api                   - Start data platform API on http://localhost:8001"
	@echo ""
	@echo "  Base Ingestion  (deterministic, frozen snapshots — used to build sicurre.db from scratch)"
	@echo "  make ingest-all-base           - Wipe DB and run ALL base ingestion steps in order"
	@echo "  make phishtank-ingest-base     - Reset DB, ingest all frozen PhishTank R2+local snapshots"
	@echo "  make file-ingest-base          - Ingest all local CSV datasets (no DB reset)"
	@echo "  make scraping-ingest-base      - Ingest frozen CERT-FR + SAP Labs snapshots (no DB reset)"
	@echo "  make db-ingest-base            - Seed external_threats.db (3-class, seed=42) + ingest into sicurre.db"
	@echo "  make bigdata-ingest-base       - Ingest R2 CC base parquet into sicurre.db"
	@echo ""
	@echo "  Cron  (scheduled, incremental — simulates production)"
	@echo "  make phishtank-cron            - Scheduled PhishTank ingestion  (set CRON_ARGS=--reserved for reserved slot)"
	@echo "  make file-cron                 - Scheduled CSV ingestion         (set CRON_ARGS=--reserved for reserved slot)"
	@echo "  make scraping-cron             - Scheduled CERT-FR scraping      (set CRON_ARGS=--reserved for reserved slot)"
	@echo "  make db-cron                   - Scheduled DB feed                (set CRON_ARGS=--reserved for reserved slot)"
	@echo "  make bigdata-cron              - Scheduled Common Crawl pipeline  (set CRON_ARGS=--reserved for reserved slot)"
	@echo "  make *-cron-reserved           - Shorthand for CRON_ARGS=--reserved make *-cron"
	@echo "  make ingest-all-cron           - Run full cron ingestion suite"
	@echo ""
	@echo "  Pipeline & Demos"
	@echo "  make pipeline-push             - Push raw data through normalize → annotate(write) → dataset-build"
	@echo "  make demo-v1                   - Full demo: base ingestion + pipeline push (dataset v1)"
	@echo "  make demo-v2                   - Full demo: generate delta + cron ingestion + pipeline push (dataset v2)"
	@echo ""
	@echo "  Dataset"
	@echo "  make generate-data             - Run canonical generation pipeline (adapted + CC lanes)"
	@echo "  make dataset-build             - Build DB-backed dataset from annotated normalized messages"
	@echo "  make dataset-export            - Serialize frozen dataset to CSV/JSONL for PyTorch"
	@echo "  make seed-frozen-dataset       - Seed current_frozen provenance into data_dataset + data_dataset_item"
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
	PYTHONPATH=src uv run uvicorn data_platform.api.main:app --reload --port 8001

test-inference:
	uv run scripts/app/test_inference_api.py

# ── Base Ingestion ─────────────────────────────────────────────────────────────

ingest-all-base: phishtank-ingest-base file-ingest-base scraping-ingest-base db-ingest-base bigdata-ingest-base
	@echo ""
	@echo "============================================================================"
	@echo "  ALL BASE INGESTION COMPLETE"
	@echo "============================================================================"
	@db_url="$${SICURRE_DATA_PLATFORM_DATABASE_URL:-sqlite+aiosqlite:///$$(pwd)/data/local/sicurre.db}"; \
	case "$$db_url" in \
	  sqlite+aiosqlite:///*) db_path="$${db_url#sqlite+aiosqlite:///}" ;; \
	  sqlite:///*) db_path="$${db_url#sqlite:///}" ;; \
	  *) db_path="" ;; \
	esac; \
	if [ -n "$$db_path" ]; then \
	  echo "  Total rows: $$(sqlite3 "$$db_path" 'SELECT COUNT(*) FROM data_raw_record')"; \
	  echo "  Database  : $$db_path"; \
	else \
	  echo "  Total rows: non disponible pour $$db_url"; \
	fi
	@echo "  Target    : 191,983"
	@echo "============================================================================"

phishtank-ingest-base:
	@db_url="$${SICURRE_DATA_PLATFORM_DATABASE_URL:-sqlite+aiosqlite:///$$(pwd)/data/local/sicurre.db}"; \
	case "$$db_url" in \
	  sqlite+aiosqlite:///*) reset_path="$${db_url#sqlite+aiosqlite:///}" ;; \
	  sqlite:///*) reset_path="$${db_url#sqlite:///}" ;; \
	  *) echo "Refusing to reset non-SQLite data-platform DB: $$db_url"; exit 1 ;; \
	esac; \
	echo "Resetting $$reset_path and running deterministic PhishTank base ingestion (R2 + local)..."; \
	rm -f "$$reset_path"
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
	@echo "Seeding external_threats.db (3-class, seed=42) then ingesting into the configured data-platform DB (deterministic)..."
	unset SICURRE_DATABASE_URL && SICURRE_DB_INGEST_FORCE_RESEED=false uv run python src/data_platform/base_ingest/db/ingest.py

# ── Cron ──────────────────────────────────────────────────────────────────────

phishtank-cron:
	@echo "Running scheduled PhishTank ingestion$(if $(CRON_ARGS), [args: $(CRON_ARGS)])..."
	uv run python src/data_platform/cron_schedulers/api/run_phishtank_ingestion.py $(CRON_ARGS)

phishtank-cron-reserved:
	$(MAKE) phishtank-cron CRON_ARGS=--reserved

file-cron:
	@echo "Running scheduled CSV ingestion$(if $(CRON_ARGS), [args: $(CRON_ARGS)])..."
	uv run python src/data_platform/cron_schedulers/file/run_csv_ingestion.py $(CRON_ARGS)

file-cron-reserved:
	$(MAKE) file-cron CRON_ARGS=--reserved

scraping-cron:
	@echo "Running scheduled CERT-FR scraping$(if $(CRON_ARGS), [args: $(CRON_ARGS)])..."
	uv run python src/data_platform/cron_schedulers/scraping/run_certfr_cti.py $(CRON_ARGS)

scraping-cron-reserved:
	$(MAKE) scraping-cron CRON_ARGS=--reserved

db-cron:
	@echo "Running scheduled DB feed$(if $(CRON_ARGS), [args: $(CRON_ARGS)])..."
	uv run python src/data_platform/cron_schedulers/database/run_sql_ingestion.py $(CRON_ARGS)

db-cron-reserved:
	$(MAKE) db-cron CRON_ARGS=--reserved

bigdata-ingest-base:
	@echo "Ingesting Common Crawl base parquet from R2 into the configured data-platform DB..."
	unset SICURRE_DATABASE_URL && uv run python src/data_platform/base_ingest/bigdata/common_crawl/ingest.py

bigdata-crawl:
	@echo "Running Common Crawl extraction to Cloudflare R2..."
	uv run python src/data_platform/cli/bigdata/common_crawl_extract.py

bigdata-ingest:
	@echo "Manually ingesting latest Common Crawl snapshot..."
	uv run python src/data_platform/cli/bigdata/common_crawl_ingest.py

bigdata-cron:
	@echo "Running scheduled Common Crawl extract→ingest pipeline$(if $(CRON_ARGS), [args: $(CRON_ARGS)])..."
	uv run python src/data_platform/cron_schedulers/bigdata/run_incremental_cc.py $(CRON_ARGS)

bigdata-cron-reserved:
	$(MAKE) bigdata-cron CRON_ARGS=--reserved

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
	@echo "Normalizing all raw records in the configured data-platform DB..."
	uv run python src/data_platform/cli/normalize/messages.py --all-pending $(NORMALIZE_ARGS)

normalize-dry:
	@echo "Previewing normalization (no DB writes)..."
	uv run python src/data_platform/cli/normalize/messages.py --dry-run $(NORMALIZE_ARGS)

# ── Annotation ────────────────────────────────────────────────────────────────

annotate:
	@echo "Persisting missing annotations on normalized messages..."
	uv run python src/data_platform/cli/maintenance/annotation_backfill.py --write

# ── Dataset ───────────────────────────────────────────────────────────────────

generate-data:
	@echo "Running canonical generation pipeline (adapted + CC lanes)..."
	uv run python src/data_platform/cli/datasets/generate.py $(GENERATE_ARGS)

dataset-build:
	@echo "Building DB-backed dataset from annotated normalized messages..."
	uv run python src/data_platform/cli/datasets/build.py \
		--name "$(DATASET_NAME)" \
		--version-tag "$(DATASET_VERSION_TAG)" \
		--target-usage "$(DATASET_TARGET_USAGE)" \
		--status "$(DATASET_STATUS)" \
		--write \
		$(DATASET_ARGS)

dataset-export:
	@echo "Serializing frozen dataset to CSV/JSONL for PyTorch..."
	uv run python src/data_platform/cli/datasets/export.py \
		--version-tag "$(DATASET_VERSION_TAG)" \
		$(EXPORT_ARGS)

seed-frozen-dataset:
	@echo "Seeding current_frozen provenance into data_dataset + data_dataset_item..."
	uv run python scripts/data_platform/seed_frozen_dataset.py $(SEED_ARGS)

# ── Pipeline & Demos ──────────────────────────────────────────────────────────

pipeline-push: normalize annotate dataset-build dataset-export
	@echo "Data pushed through normalization, annotation, dataset build, and dataset export."

demo-v1: ingest-all-base
	@echo "Running canonical generation lanes before pipeline push..."
	$(MAKE) generate-data
	$(MAKE) pipeline-push
	@echo "Demo V1 Dataset Generated"

demo-v2:
	@echo "Simulating time passage: Generating 50 new external threat records..."
	uv run python src/data_platform/cli/generate_sql_delta.py -n 50
	@echo "Running cron..."
	$(MAKE) ingest-all-cron
	@echo "Pushing new data through pipeline..."
	$(MAKE) pipeline-push DATASET_TAG_PREFIX=cron
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
