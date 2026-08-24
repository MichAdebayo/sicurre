.PHONY: help install test dev-api poc-inference-smoke poc-ui-smoke openapi openapi-check \
        ingest-all-base \
        data-platform-staging-smoke \
        app-stack-smoke \
        grafana-provision \
        phishtank-ingest-base \
        file-ingest-base \
        scraping-ingest-base \
        db-ingest-base \
        bigdata-ingest-base \
        phishtank-cron file-cron scraping-cron sekoia-cron db-cron bigdata-cron \
        phishtank-cron-reserved file-cron-reserved scraping-cron-reserved sekoia-cron-reserved \
        db-cron-reserved bigdata-cron-reserved \
        cron-orchestrate ingest-all-cron run-scheduler \
        bigdata-crawl bigdata-ingest bigdata-reviewed-promote \
        normalize normalize-dry \
        annotate \
        generate-data dataset-build dataset-export publish-latest dataset-release monthly-release \
        seed-frozen-dataset \
		poc-replay-frozen poc-inference \
		poc-cron-demo poc-release-preview poc-staging-publish \
        pipeline-push run-pipeline demo-v1 demo-v2 \
        poc db-seed r2-freeze-proof dev-api dev-app dev-stop dev

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
	@echo "  make openapi                   - Regenerate docs/api/openapi.yaml from FastAPI"
	@echo "  make openapi-check             - Fail when the generated OpenAPI contract is stale"
	@echo "  make poc-inference-smoke       - Test authenticated local POC inference"
	@echo "  make poc-ui-smoke              - Run the deterministic POC UI logic suite"
	@echo "  make dev-api                   - Start data platform API on http://localhost:8001"
	@echo "  make data-platform-staging-smoke - Build and smoke-test data platform container"
	@echo "  make app-stack-smoke           - Build and smoke-test app + auth + API containers"
	@echo "  make grafana-provision         - Provision Sicurre Grafana dashboard"
	@echo "  make ci-data-quality           - Run critical Python lint, typing, docs, and coverage gates"
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
	@echo "  make sekoia-cron               - Scheduled SEKOIA IOC ingestion  (set CRON_ARGS=--reserved for reserved slot)"
	@echo "  make db-cron                   - Scheduled DB feed                (set CRON_ARGS=--reserved for reserved slot)"
	@echo "  make bigdata-cron              - Scheduled Common Crawl pipeline  (set CRON_ARGS=--reserved for reserved slot)"
	@echo "  make *-cron-reserved           - Shorthand for CRON_ARGS=--reserved make *-cron"
	@echo "  make run-scheduler             - Run all scheduled ingestion tasks sequentially"
	@echo ""
	@echo "  Pipeline Execution"
	@echo "  make pipeline-push             - Normalize, annotate, build a dataset, and export it locally/R2"
	@echo "  make dataset-release           - Monthly release: normalize, annotate, build, export, publish, dispatch ML"
	@echo "  make run-pipeline              - Legacy manual all-in-one: cron suite + dataset-release"
	@echo "  make demo-v1                   - Legacy/demo alias: base ingestion + pipeline push"
	@echo "  make demo-v2                   - Legacy/demo alias: run-pipeline with mock delta generator"
	@echo ""
	@echo "  Dataset"
	@echo "  make generate-data             - Run canonical generation pipeline (adapted + CC lanes)"
	@echo "  make dataset-build             - Build DB-backed dataset from annotated normalized messages"
	@echo "  make dataset-export            - Serialize frozen dataset to CSV/JSONL for PyTorch"
	@echo "  make seed-frozen-dataset       - Seed current_frozen provenance into data_dataset + data_dataset_item"
	@echo "  make poc-replay-frozen         - Idempotent replay of frozen production dataset lineage for POC"
	@echo "  make poc-cron-demo             - Run the isolated SEKOIA scheduled ingestion demonstration"
	@echo "  make poc-release-preview       - Build and export a local POC dataset without publication"
	@echo "  make poc-staging-publish       - Publish only to the explicit POC staging Kaggle slug"
	@echo ""
	@echo "  POC"
	@echo "  make poc                       - Launch Streamlit POC dashboard"
	@echo "  make poc-inference             - Launch Sicurre-ML with the POC bearer key"
	@echo ""
	@echo "  Dev"
	@echo "  make db-seed                   - Manually seed external_threats.db (dev utility)"

install:
	uv sync

test: test-unit test-integration

test-unit:
	uv run pytest tests/unit

test-integration:
	uv run pytest tests/integration

openapi:
	uv run --no-sync python scripts/data_platform/generate_openapi.py

openapi-check:
	uv run --no-sync python scripts/data_platform/generate_openapi.py --check

dev-api:
	@pids="$$(pgrep -f 'uvicorn data_platform.api.main:app --reload --port 8001' 2>/dev/null) $$(lsof -tiTCP:8001 -sTCP:LISTEN 2>/dev/null)"; \
	if [ -n "$$pids" ]; then \
		echo "Stopping existing local Sicurre API on port 8001..."; \
		kill $$pids 2>/dev/null || true; \
		for attempt in 1 2 3 4 5; do \
			lsof -tiTCP:8001 -sTCP:LISTEN >/dev/null 2>&1 || break; \
			sleep 0.2; \
		done; \
		remaining=$$(lsof -tiTCP:8001 -sTCP:LISTEN 2>/dev/null); \
		[ -z "$$remaining" ] || kill -KILL $$remaining 2>/dev/null || true; \
	fi
	PYTHONPATH=src uv run uvicorn data_platform.api.main:app --reload --port 8001

dev-app:
	npm run dev

dev-stop:
	@for port in 3005 5173 5174 8001; do \
		pids=$$(lsof -tiTCP:$$port -sTCP:LISTEN 2>/dev/null); \
		if [ -n "$$pids" ]; then \
			echo "Stopping existing Sicurre development service on port $$port..."; \
			kill $$pids 2>/dev/null || true; \
		fi; \
	done
	@sleep 0.5
	@for port in 3005 5173 5174 8001; do \
		pids=$$(lsof -tiTCP:$$port -sTCP:LISTEN 2>/dev/null); \
		[ -z "$$pids" ] || kill -KILL $$pids 2>/dev/null || true; \
	done

dev: dev-stop
	npx --yes concurrently --kill-others "make dev-api" "make dev-app" "npm run auth:dev"

data-platform-staging-smoke:
	docker compose -f docker-compose.data-platform-smoke.yml up --build --abort-on-container-exit --exit-code-from data-platform-smoke

app-stack-smoke:
	docker compose -f docker-compose.app-smoke.yml up --build --abort-on-container-exit --exit-code-from app-smoke

grafana-provision:
	node scripts/deploy/provision_grafana_dashboard.mjs

ci-data-quality:
	uv run --group backend --group dev --group storage ruff check src/core/config.py src/data_platform/extractors/incremental_cc_extractor.py src/data_platform/cron_schedulers/bigdata/run_incremental_cc.py tests/integration/data_platform/common_crawl/test_incremental_cc_checkpoint.py tests/unit/data_platform/common_crawl/test_cc_runtime_config.py
	uv run --group backend --group dev --group storage ruff format --check src/core/config.py src/data_platform/extractors/incremental_cc_extractor.py src/data_platform/cron_schedulers/bigdata/run_incremental_cc.py tests/integration/data_platform/common_crawl/test_incremental_cc_checkpoint.py tests/unit/data_platform/common_crawl/test_cc_runtime_config.py
	uv run --group backend --group dev --group storage mypy --config-file mypy.ini --follow-imports=skip
	uv run --group backend --group dev --group storage interrogate -f 90 src/core/config.py src/data_platform/extractors/incremental_cc_extractor.py src/data_platform/cron_schedulers/bigdata/run_incremental_cc.py
	uv run --group backend --group dev --group storage pytest tests/unit tests/integration --cov=src --cov-branch --cov-report=term-missing --cov-fail-under=50
	uv run --group backend --group dev --group storage pytest tests/unit tests/integration --cov=src/core --cov=src/db --cov-branch --cov-report=term-missing --cov-fail-under=90
	npm run test:coverage

poc-inference-smoke:
	PYTHONPATH=src uv run python tests/e2e/poc/smoke_local_inference.py

poc-ui-smoke:
	uv run pytest tests/unit/poc -q

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

sekoia-cron:
	@echo "Running scheduled SEKOIA IOC ingestion$(if $(CRON_ARGS), [args: $(CRON_ARGS)])..."
	uv run python src/data_platform/cron_schedulers/scraping/run_sekoia_ioc.py $(CRON_ARGS)

sekoia-cron-reserved:
	$(MAKE) sekoia-cron CRON_ARGS=--reserved

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

run-scheduler: cron-orchestrate
	@echo "All cron ingestion tasks completed."

ingest-all-cron: run-scheduler

# ── Normalization ─────────────────────────────────────────────────────────────

normalize:
	@echo "Normalizing all raw records in the configured data-platform DB..."
	uv run --no-sync python src/data_platform/cli/normalize/messages.py --all-pending $(NORMALIZE_ARGS)

normalize-dry:
	@echo "Previewing normalization (no DB writes)..."
	uv run python src/data_platform/cli/normalize/messages.py --dry-run $(NORMALIZE_ARGS)

# ── Annotation ────────────────────────────────────────────────────────────────

annotate:
	@echo "Persisting missing annotations on normalized messages..."
	uv run --no-sync python src/data_platform/cli/maintenance/annotation_backfill.py --write

# ── Dataset ───────────────────────────────────────────────────────────────────

generate-data:
	@echo "Running canonical generation pipeline (adapted + CC lanes)..."
	uv run python src/data_platform/cli/datasets/generate.py $(GENERATE_ARGS)

dataset-build:
	@echo "Building DB-backed dataset from annotated normalized messages..."
	uv run --no-sync python src/data_platform/cli/datasets/build.py \
		--name "$(DATASET_NAME)" \
		--version-tag "$(DATASET_VERSION_TAG)" \
		--target-usage "$(DATASET_TARGET_USAGE)" \
		--status "$(DATASET_STATUS)" \
		--write \
		$(DATASET_ARGS)

dataset-export:
	@echo "Serializing frozen dataset to CSV/JSONL for PyTorch..."
	uv run --no-sync python src/data_platform/cli/datasets/export.py \
		--version-tag "$(DATASET_VERSION_TAG)" \
		$(EXPORT_ARGS)

publish-latest:
	@echo "Publishing latest frozen dataset to Kaggle and dispatching ML training..."
	uv run --no-sync python scripts/data_platform/publish_latest.py

seed-frozen-dataset:
	@echo "Seeding current_frozen provenance into data_dataset + data_dataset_item..."
	uv run python scripts/data_platform/seed_frozen_dataset.py $(SEED_ARGS)

poc-replay-frozen:
	@echo "Running deterministic POC replay from frozen provenance (with local data DB reset)..."
	@uv run --env-file .env sh -c 'set -eu; \
	db_url="$$SICURRE_POC_DATA_PLATFORM_DATABASE_URL"; \
	case "$$db_url" in \
	  sqlite+aiosqlite:///*) reset_path="$${db_url#sqlite+aiosqlite:///}" ;; \
	  sqlite:///*) reset_path="$${db_url#sqlite:///}" ;; \
	  *) echo "Refusing to reset non-SQLite data-platform DB: $$db_url"; exit 1 ;; \
	esac; \
	echo "Resetting $$reset_path"; \
	rm -f "$$reset_path" "$$reset_path-shm" "$$reset_path-wal"; \
	export PYTHONPATH=src SICURRE_POC_MODE=true SICURRE_DATA_PLATFORM_DATABASE_URL="$$db_url"; \
	uv run alembic upgrade head; \
	$(MAKE) normalize; \
	$(MAKE) annotate; \
	$(MAKE) seed-frozen-dataset SEED_ARGS="--materialize-missing --sync-existing-version"; \
	uv run --no-sync python -m poc.seed_api_evidence'
	@echo "POC frozen replay completed: deterministic parity synced to current_frozen."

poc-cron-demo:
	@echo "Running SEKOIA read-only fetch with local POC snapshot and SQLite persistence..."
	@uv run --env-file .env sh -c 'SICURRE_POC_MODE=true \
		SICURRE_DATA_PLATFORM_DATABASE_URL="$$SICURRE_POC_DATA_PLATFORM_DATABASE_URL" \
		SICURRE_SEKOIA_SNAPSHOT_STORAGE_BACKEND=local PYTHONPATH=src \
		python src/data_platform/cron_schedulers/scraping/run_sekoia_ioc.py'

poc-release-preview:
	@uv run --env-file .env sh -c 'set -eu; SICURRE_POC_MODE=true \
		SICURRE_DATA_PLATFORM_DATABASE_URL="$$SICURRE_POC_DATA_PLATFORM_DATABASE_URL" \
		SICURRE_TRAINING_DATASET_SNAPSHOT_STORAGE_BACKEND=local \
		$(MAKE) normalize annotate; \
		set +e; PYTHONPATH=src python -m poc.release_preflight; code=$$?; set -e; \
		if [ $$code -eq 3 ]; then exit 0; fi; \
		test $$code -eq 0; \
		SICURRE_POC_MODE=true \
		SICURRE_DATA_PLATFORM_DATABASE_URL="$$SICURRE_POC_DATA_PLATFORM_DATABASE_URL" \
		SICURRE_TRAINING_DATASET_SNAPSHOT_STORAGE_BACKEND=local \
		$(MAKE) dataset-build dataset-export DATASET_TAG_PREFIX=poc-preview'
	@echo "POC release preview completed locally. No Kaggle publication or ML dispatch occurred."

poc-staging-publish:
	@uv run --env-file .env sh -c 'set -eu; \
		test "$${SICURRE_POC_ALLOW_STAGING_PUBLICATION:-false}" = "true" || \
		{ echo "Set SICURRE_POC_ALLOW_STAGING_PUBLICATION=true for staging publication."; exit 1; }; \
		test -n "$${SICURRE_POC_KAGGLE_DATASET_SLUG:-}" || \
		{ echo "SICURRE_POC_KAGGLE_DATASET_SLUG is required."; exit 1; }; \
		test "$${SICURRE_POC_ALLOW_ML_DISPATCH:-false}" != "true" || \
		{ echo "ML dispatch is forbidden from the POC staging publisher."; exit 1; }; \
		SICURRE_POC_MODE=true KAGGLE_DATASET_SLUG="$$SICURRE_POC_KAGGLE_DATASET_SLUG" \
		python scripts/data_platform/publish_latest.py --skip-github-dispatch'

# ── Pipeline & Demos ──────────────────────────────────────────────────────────

pipeline-push: normalize annotate dataset-build dataset-export
	@echo "Data pushed through normalization, annotation, dataset build, and dataset export."

dataset-release: normalize annotate dataset-build dataset-export publish-latest
	@echo "Monthly dataset release completed."

monthly-release: normalize annotate
	@set +e; uv run --no-sync python scripts/data_platform/release_preflight.py; code=$$?; set -e; \
	if [ $$code -eq 3 ]; then echo "Monthly release skipped: no new eligible records."; exit 0; fi; \
	if [ $$code -ne 0 ]; then exit $$code; fi; \
	$(MAKE) dataset-build dataset-export publish-latest

run-pipeline: run-scheduler
	$(MAKE) dataset-release DATASET_TAG_PREFIX=cron
	@echo "Legacy end-to-end scheduler run and dataset release completed."

demo-v1: ingest-all-base
	@echo "Running canonical generation lanes before pipeline push..."
	$(MAKE) generate-data
	$(MAKE) pipeline-push
	@echo "Demo V1 Dataset Generated"

demo-v2:
	@echo "Simulating time passage: Generating 50 new external threat records..."
	uv run python src/data_platform/cli/generate_sql_delta.py -n 50
	$(MAKE) run-pipeline
	@echo "Demo V2 Dataset Generated"

# ── POC ───────────────────────────────────────────────────────────────────────

SICURRE_ML_REPO ?= ../sicurre-ml

poc-inference:
	@test -f .env || (echo "ERROR: root .env is required" && exit 1)
	@test -f "$(SICURRE_ML_REPO)/Makefile" || (echo "ERROR: Sicurre-ML repository not found at $(SICURRE_ML_REPO)" && exit 1)
	@set -a; . ./.env; set +a; \
		test -n "$$SICURRE_POC_INFERENCE_API_KEY" || (echo "ERROR: SICURRE_POC_INFERENCE_API_KEY is missing" && exit 1); \
		status=$$(curl --silent --output /dev/null --write-out "%{http_code}" \
			--header "Authorization: Bearer $$SICURRE_POC_INFERENCE_API_KEY" \
			--header "Content-Type: application/json" \
			--data '{}' "$$SICURRE_POC_INFERENCE_API_URL" || true); \
		if [ "$$status" = "422" ]; then \
			echo "Sicurre-ML is already running and accepts the POC bearer key."; \
			exit 0; \
		fi; \
		if [ "$$status" = "401" ]; then \
			echo "ERROR: port 8000 is serving Sicurre-ML with a different bearer key."; \
			echo "Stop that process, then run make poc-inference again."; \
			exit 1; \
		fi; \
		cd "$(SICURRE_ML_REPO)"; \
		INFERENCE_API_KEY="$$SICURRE_POC_INFERENCE_API_KEY" $(MAKE) serve-reload

poc-seed:
	@echo "Seeding POC users (admin + demo)..."
	PYTHONPATH=src uv run python -m poc.seed_users

poc: poc-seed
	@echo "Starting Sicurre POC Streamlit Dashboard..."
	PYTHONPATH=src uv run streamlit run src/poc/app.py --server.port 8501

# ── Dev ───────────────────────────────────────────────────────────────────────

db-seed:
	@echo "Manually seeding external_threats.db (dev utility)..."
	uv run python src/data_platform/cli/dev/seed_external_db.py

# ── R2 Freeze Proof ───────────────────────────────────────────────────────────

r2-freeze-proof:
	@echo "Uploading all source files to R2 base/ prefixes and verifying counts..."
	@echo "sicurre.db BEFORE: $$(sqlite3 data/local/sicurre.db 'SELECT COUNT(*) FROM data_raw_record') rows"
	unset SICURRE_DATABASE_URL && uv run python scripts/data_platform/shared/r2_freeze_proof/run_all.py
