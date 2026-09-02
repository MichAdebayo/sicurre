# Sicurre - data platform, POC and app orchestration.
#
# Targets are grouped by STAGE, not by step. The pipeline runs in one direction:
#
#     collect  ->  process  ->  release
#     (ingest)     (normalize,   (build, export,
#                   generate,     publish, dispatch ML)
#                   annotate)
#
# Each stage has a single entry point; the per-step targets below it still exist
# and are still individually runnable, because debugging a stage means running
# one step at a time. What changed is that the stage now names the sequence, so
# a step that belongs to a stage and is missing from it is visible rather than
# implied. That gap is not hypothetical: generate-data was a working target with
# no caller in the monthly release for months, and the release quietly shipped
# without a generation pass because nothing declared the sequence in one place.

# ── Source table ──────────────────────────────────────────────────────────────
# Six sources, each with a scheduled ingestion script. Previously this was
# twelve near-identical targets (six *-cron plus six *-cron-reserved wrappers);
# the pattern rules further down derive all twelve from this table, so adding a
# source means adding one line here rather than two targets and two .PHONY
# entries.
SOURCES := phishtank file scraping sekoia db bigdata

CRON_SCRIPT_phishtank := api/run_phishtank_ingestion.py
CRON_SCRIPT_file      := file/run_csv_ingestion.py
CRON_SCRIPT_scraping  := scraping/run_certfr_cti.py
CRON_SCRIPT_sekoia    := scraping/run_sekoia_ioc.py
CRON_SCRIPT_db        := database/run_sql_ingestion.py
CRON_SCRIPT_bigdata   := bigdata/run_incremental_cc.py

CRON_LABEL_phishtank := PhishTank ingestion
CRON_LABEL_file      := CSV ingestion
CRON_LABEL_scraping  := CERT-FR scraping
CRON_LABEL_sekoia    := SEKOIA IOC ingestion
CRON_LABEL_db        := DB feed
CRON_LABEL_bigdata   := Common Crawl extract->ingest pipeline

# ── Tunables ──────────────────────────────────────────────────────────────────
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
SEED_ARGS ?=
SICURRE_ML_REPO ?= ../sicurre-ml

# Resolve the configured data-platform DB to a filesystem path, or empty when it
# is not SQLite. Defined once because three targets needed the same case block.
define resolve_sqlite_path
db_url="$${SICURRE_DATA_PLATFORM_DATABASE_URL:-sqlite+aiosqlite:///$$(pwd)/data/local/sicurre.db}"; \
case "$$db_url" in \
  sqlite+aiosqlite:///*) db_path="$${db_url#sqlite+aiosqlite:///}" ;; \
  sqlite:///*) db_path="$${db_url#sqlite:///}" ;; \
  *) db_path="" ;; \
esac
endef

.PHONY: help \
        check install test test-unit test-integration openapi openapi-check ci-data-quality \
        data-platform-staging-smoke app-stack-smoke poc-inference-smoke poc-ui-smoke grafana-provision \
        collect ingest-all-base phishtank-ingest-base file-ingest-base scraping-ingest-base \
        db-ingest-base bigdata-ingest-base \
        cron-orchestrate run-scheduler ingest-all-cron \
        bigdata-crawl bigdata-ingest bigdata-reviewed-promote \
        process normalize normalize-dry generate-data annotate \
        release dataset-build dataset-export publish-latest dataset-release monthly-release \
        pipeline-push seed-frozen-dataset \
        run-pipeline demo-v1 demo-v2 \
        poc poc-seed poc-stop poc-inference poc-inference-stop \
        poc-replay-frozen poc-cron-demo poc-release-preview \
        db-seed r2-freeze-proof dev dev-api dev-app dev-stop

help:
	@echo "Sicurre - Available Commands"
	@echo ""
	@echo "  STAGES  (the pipeline, in order)"
	@echo "  make collect                   - Run the scheduled ingestion suite for all six sources"
	@echo "  make process                   - Normalize, run generation lanes, then annotate"
	@echo "  make release                   - Monthly release: process, preflight, build, export, publish"
	@echo "  make check                     - Tests, OpenAPI contract, lint/typing/coverage gates"
	@echo ""
	@echo "  Setup"
	@echo "  make install                   - Install local python dependencies"
	@echo "  make test                      - Run backend test suite (unit + integration)"
	@echo "  make openapi                   - Regenerate docs/api/openapi.yaml from FastAPI"
	@echo "  make openapi-check             - Fail when the generated OpenAPI contract is stale"
	@echo "  make ci-data-quality           - Run critical Python lint, typing, docs, and coverage gates"
	@echo "  make data-platform-staging-smoke - Build and smoke-test data platform container"
	@echo "  make app-stack-smoke           - Build and smoke-test app + auth + API containers"
	@echo "  make grafana-provision         - Provision Sicurre Grafana dashboard"
	@echo ""
	@echo "  Collect - base  (deterministic, frozen snapshots; builds sicurre.db from scratch)"
	@echo "  make ingest-all-base           - Wipe DB and run ALL base ingestion steps in order"
	@echo "  make phishtank-ingest-base     - Reset DB, ingest all frozen PhishTank R2+local snapshots"
	@echo "  make file-ingest-base          - Ingest all local CSV datasets (no DB reset)"
	@echo "  make scraping-ingest-base      - Ingest frozen CERT-FR + SAP Labs snapshots (no DB reset)"
	@echo "  make db-ingest-base            - Seed external_threats.db (3-class, seed=42) + ingest"
	@echo "  make bigdata-ingest-base       - Ingest R2 CC base parquet into sicurre.db"
	@echo ""
	@echo "  Collect - scheduled  (incremental; simulates production)"
	@echo "  make <source>-cron             - Scheduled ingestion for one source"
	@echo "                                   sources: $(SOURCES)"
	@echo "  make <source>-cron-reserved    - Shorthand for CRON_ARGS=--reserved make <source>-cron"
	@echo "  make collect                   - All six, sequentially, via the orchestrator"
	@echo "  make bigdata-crawl             - Common Crawl extraction to Cloudflare R2"
	@echo "  make bigdata-ingest            - Manually ingest the latest Common Crawl snapshot"
	@echo "  make bigdata-reviewed-promote  - Promote reviewed CC exports into curated tables"
	@echo ""
	@echo "  Process"
	@echo "  make normalize                 - Normalize all pending raw records"
	@echo "  make normalize-dry             - Preview normalization without DB writes"
	@echo "  make generate-data             - Run generation lanes (adapted + Common Crawl + CERT-FR)"
	@echo "  make annotate                  - Persist missing annotations on normalized messages"
	@echo ""
	@echo "  Release"
	@echo "  make dataset-build             - Build DB-backed dataset from annotated messages"
	@echo "  make dataset-export            - Serialize frozen dataset to CSV/JSONL for PyTorch"
	@echo "  make publish-latest            - Publish to Kaggle and dispatch ML training"
	@echo "  make pipeline-push             - process + build + export, no publication"
	@echo "  make seed-frozen-dataset       - Seed current_frozen provenance into data_dataset"
	@echo ""
	@echo "  POC"
	@echo "  make poc                       - Launch Streamlit POC dashboard"
	@echo "  make poc-stop                  - Stop the POC and free port 8501"
	@echo "  make poc-inference             - Launch Sicurre-ML with the POC bearer key"
	@echo "  make poc-inference-stop        - Stop local Sicurre-ML and free port 8000"
	@echo "  make poc-replay-frozen         - Idempotent replay of frozen dataset lineage"
	@echo "  make poc-cron-demo             - Isolated SEKOIA scheduled ingestion demonstration"
	@echo "  make poc-release-preview       - Build and export a local POC dataset, no publication"
	@echo ""
	@echo "  Dev"
	@echo "  make dev                       - API + app + auth together"
	@echo "  make dev-api                   - Data platform API on http://localhost:8001"
	@echo "  make dev-stop                  - Free ports 3005, 5173, 5174, 8001"
	@echo "  make db-seed                   - Manually seed external_threats.db (dev utility)"
	@echo "  make r2-freeze-proof           - Upload sources to R2 base/ prefixes and verify counts"
	@echo ""
	@echo "  Legacy aliases: run-scheduler, ingest-all-cron, dataset-release, run-pipeline, demo-v1, demo-v2"

# ══ Setup and checks ═══════════════════════════════════════════════════════════

install:
	uv sync

check: test openapi-check
	@echo "Tests and OpenAPI contract are green."

test: test-unit test-integration

test-unit:
	uv run pytest tests/unit

test-integration:
	uv run pytest tests/integration

openapi:
	uv run --no-sync python scripts/data_platform/generate_openapi.py

openapi-check:
	uv run --no-sync python scripts/data_platform/generate_openapi.py --check

ci-data-quality:
	uv run --group backend --group dev --group storage ruff check src/core/config.py src/data_platform/extractors/incremental_cc_extractor.py src/data_platform/cron_schedulers/bigdata/run_incremental_cc.py tests/integration/data_platform/common_crawl/test_incremental_cc_checkpoint.py tests/unit/data_platform/common_crawl/test_cc_runtime_config.py
	uv run --group backend --group dev --group storage ruff format --check src/core/config.py src/data_platform/extractors/incremental_cc_extractor.py src/data_platform/cron_schedulers/bigdata/run_incremental_cc.py tests/integration/data_platform/common_crawl/test_incremental_cc_checkpoint.py tests/unit/data_platform/common_crawl/test_cc_runtime_config.py
	uv run --group backend --group dev --group storage mypy --config-file mypy.ini --follow-imports=skip
	uv run --group backend --group dev --group storage interrogate -f 90 src/core/config.py src/data_platform/extractors/incremental_cc_extractor.py src/data_platform/cron_schedulers/bigdata/run_incremental_cc.py
	uv run --group backend --group dev --group storage pytest tests/unit tests/integration --cov=src --cov-branch --cov-report=term-missing --cov-fail-under=50
	uv run --group backend --group dev --group storage pytest tests/unit tests/integration --cov=src/core --cov=src/db --cov-branch --cov-report=term-missing --cov-fail-under=90
	npm run test:coverage

data-platform-staging-smoke:
	docker compose -f docker-compose.data-platform-smoke.yml up --build --abort-on-container-exit --exit-code-from data-platform-smoke

app-stack-smoke:
	docker compose -f docker-compose.app-smoke.yml up --build --abort-on-container-exit --exit-code-from app-smoke

grafana-provision:
	node scripts/deploy/provision_grafana_dashboard.mjs

poc-inference-smoke:
	PYTHONPATH=src uv run python tests/e2e/poc/smoke_local_inference.py

poc-ui-smoke:
	uv run pytest tests/unit/poc -q

# ══ COLLECT ════════════════════════════════════════════════════════════════════
# Base ingestion stays explicit per source: the steps genuinely differ (only
# PhishTank resets the DB, only scraping runs two scripts, only db and bigdata
# need SICURRE_DATABASE_URL unset). Collapsing them into a pattern rule would
# hide those differences rather than remove them.

ingest-all-base: phishtank-ingest-base file-ingest-base scraping-ingest-base db-ingest-base bigdata-ingest-base
	@echo ""
	@echo "============================================================================"
	@echo "  ALL BASE INGESTION COMPLETE"
	@echo "============================================================================"
	@$(resolve_sqlite_path); \
	if [ -n "$$db_path" ]; then \
	  echo "  Total rows: $$(sqlite3 "$$db_path" 'SELECT COUNT(*) FROM data_raw_record')"; \
	  echo "  Database  : $$db_path"; \
	else \
	  echo "  Total rows: non disponible pour $$db_url"; \
	fi
	@echo "  Target    : 191,983"
	@echo "============================================================================"

phishtank-ingest-base:
	@$(resolve_sqlite_path); \
	test -n "$$db_path" || { echo "Refusing to reset non-SQLite data-platform DB: $$db_url"; exit 1; }; \
	echo "Resetting $$db_path and running deterministic PhishTank base ingestion (R2 + local)..."; \
	rm -f "$$db_path"
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

bigdata-ingest-base:
	@echo "Ingesting Common Crawl base parquet from R2 into the configured data-platform DB..."
	unset SICURRE_DATABASE_URL && uv run python src/data_platform/base_ingest/bigdata/common_crawl/ingest.py

# Scheduled ingestion: two pattern rules replace twelve hand-written targets.
# Deliberately NOT in .PHONY: listing a name there gives it an explicit
# recipe-less rule that wins over the pattern rule, and make answers
# "Nothing to be done" instead of ingesting. No files carry these names, so
# the pattern rules run as-is.
# An unknown source fails loudly instead of matching the pattern and doing
# nothing, which is the failure mode a bare pattern rule would introduce.
%-cron:
	@script="$(CRON_SCRIPT_$*)"; \
	if [ -z "$$script" ]; then \
	  echo "Unknown ingestion source '$*'. Known sources: $(SOURCES)"; \
	  exit 1; \
	fi; \
	echo "Running scheduled $(CRON_LABEL_$*)$(if $(CRON_ARGS), [args: $(CRON_ARGS)])..."; \
	uv run python "src/data_platform/cron_schedulers/$$script" $(CRON_ARGS)

%-cron-reserved:
	$(MAKE) $*-cron CRON_ARGS=--reserved

cron-orchestrate:
	@echo "Running full cron suite manually..."
	uv run python src/data_platform/cli/maintenance/cron_orchestrator.py $(CRON_ARGS)

collect: cron-orchestrate
	@echo "All scheduled ingestion tasks completed."

run-scheduler: collect
ingest-all-cron: collect

bigdata-crawl:
	@echo "Running Common Crawl extraction to Cloudflare R2..."
	uv run python src/data_platform/cli/bigdata/common_crawl_extract.py

bigdata-ingest:
	@echo "Manually ingesting latest Common Crawl snapshot..."
	uv run python src/data_platform/cli/bigdata/common_crawl_ingest.py

bigdata-reviewed-promote:
	@echo "Promoting reviewed Common Crawl exports into curated tables..."
	uv run python src/data_platform/cli/bigdata/common_crawl_reviewed_promotion.py $(BIGDATA_PROMOTION_ARGS)

# ══ PROCESS ════════════════════════════════════════════════════════════════════
# Order is load-bearing. Generation produces new normalized messages, so it runs
# after normalize and before annotate; putting it last leaves its output
# unannotated and invisible to the release preflight.

process: normalize generate-data annotate
	@echo "Raw records normalized, generation lanes run, annotations persisted."

normalize:
	@echo "Normalizing all raw records in the configured data-platform DB..."
	uv run --no-sync python src/data_platform/cli/normalize/messages.py --all-pending $(NORMALIZE_ARGS)

normalize-dry:
	@echo "Previewing normalization (no DB writes)..."
	uv run python src/data_platform/cli/normalize/messages.py --dry-run $(NORMALIZE_ARGS)

# --no-sync is load-bearing here, not cosmetic. The release image installs only
# the runtime and release groups (uv sync --frozen --no-default-groups). A bare
# `uv run` re-syncs to the DEFAULT groups, which tears out the release group -
# kaggle, which publish-latest needs - and pulls dev dependencies the image was
# deliberately built without. Every other step in the release path already
# passes --no-sync; this one did not, and it was the only one that did not.
generate-data:
	@echo "Running canonical generation pipeline (adapted + Common Crawl + CERT-FR lanes)..."
	uv run --no-sync python src/data_platform/cli/datasets/generate.py $(GENERATE_ARGS)

annotate:
	@echo "Persisting missing annotations on normalized messages..."
	uv run --no-sync python src/data_platform/cli/maintenance/annotation_backfill.py --write

# ══ RELEASE ════════════════════════════════════════════════════════════════════

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

# The monthly release. Preflight exit code 3 means "no new eligible records",
# which is a clean no-op rather than a failure.
release: process
	@set +e; uv run --no-sync python scripts/data_platform/release_preflight.py; code=$$?; set -e; \
	if [ $$code -eq 3 ]; then echo "Monthly release skipped: no new eligible records."; exit 0; fi; \
	if [ $$code -ne 0 ]; then exit $$code; fi; \
	$(MAKE) dataset-build dataset-export publish-latest

monthly-release: release

pipeline-push: process dataset-build dataset-export
	@echo "Data pushed through processing, dataset build, and dataset export."

dataset-release: process dataset-build dataset-export publish-latest
	@echo "Dataset release completed."

# ══ Legacy and demo aliases ════════════════════════════════════════════════════

run-pipeline: collect
	$(MAKE) dataset-release DATASET_TAG_PREFIX=cron
	@echo "Legacy end-to-end scheduler run and dataset release completed."

demo-v1: ingest-all-base
	$(MAKE) pipeline-push
	@echo "Demo V1 Dataset Generated"

demo-v2:
	@echo "Simulating time passage: Generating 50 new external threat records..."
	uv run python src/data_platform/cli/generate_sql_delta.py -n 50
	$(MAKE) run-pipeline
	@echo "Demo V2 Dataset Generated"

# ══ POC ════════════════════════════════════════════════════════════════════════

poc-seed:
	@echo "Seeding POC users (admin + demo)..."
	PYTHONPATH=src uv run python -m poc.seed_users

poc: poc-seed
	@$(MAKE) poc-stop
	@echo "Starting Sicurre POC Streamlit Dashboard..."
	PYTHONPATH=src uv run streamlit run src/poc/app.py --server.port 8501

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

poc-inference-stop:
	@$(MAKE) --no-print-directory _free-port PORT=8000 LABEL="Sicurre-ML"

poc-stop:
	@$(MAKE) --no-print-directory _free-port PORT=8501 LABEL="Sicurre POC"

# ══ Dev ════════════════════════════════════════════════════════════════════════

dev: dev-stop
	npx --yes concurrently --kill-others "make dev-api" "make dev-app" "npm run auth:dev"

dev-api:
	@pids=$$(pgrep -f 'uvicorn data_platform.api.main:app --reload --port 8001' 2>/dev/null); \
	[ -z "$$pids" ] || { echo "Stopping half-started Sicurre API..."; kill $$pids 2>/dev/null || true; }
	@$(MAKE) --no-print-directory _free-port PORT=8001 LABEL="local Sicurre API" QUIET=1
	PYTHONPATH=src uv run uvicorn data_platform.api.main:app --reload --port 8001

dev-app:
	npm run dev

dev-stop:
	@for port in 3005 5173 5174 8001; do \
		$(MAKE) --no-print-directory _free-port PORT=$$port LABEL="Sicurre development service" QUIET=1 || true; \
	done

db-seed:
	@echo "Manually seeding external_threats.db (dev utility)..."
	uv run python src/data_platform/cli/dev/seed_external_db.py

r2-freeze-proof:
	@echo "Uploading all source files to R2 base/ prefixes and verifying counts..."
	@echo "sicurre.db BEFORE: $$(sqlite3 data/local/sicurre.db 'SELECT COUNT(*) FROM data_raw_record') rows"
	unset SICURRE_DATABASE_URL && uv run python scripts/data_platform/shared/r2_freeze_proof/run_all.py

# Internal: graceful-then-forced shutdown of whatever holds PORT. Four targets
# had four near-identical copies of this loop, each with its own retry count.
.PHONY: _free-port
_free-port:
	@pids=$$(lsof -tiTCP:$(PORT) -sTCP:LISTEN 2>/dev/null | sort -u); \
	if [ -z "$$pids" ]; then \
	  [ -n "$(QUIET)" ] || echo "$(LABEL) is not running; port $(PORT) is free."; \
	  exit 0; \
	fi; \
	echo "Stopping $(LABEL) on port $(PORT) (PID: $$(echo $$pids | tr '\n' ' '))..."; \
	kill $$pids 2>/dev/null || true; \
	for attempt in 1 2 3 4 5 6 7 8 9 10; do \
	  lsof -tiTCP:$(PORT) -sTCP:LISTEN >/dev/null 2>&1 || break; \
	  sleep 0.2; \
	done; \
	remaining=$$(lsof -tiTCP:$(PORT) -sTCP:LISTEN 2>/dev/null | sort -u); \
	if [ -n "$$remaining" ]; then \
	  echo "$(LABEL) did not stop gracefully; forcing shutdown..."; \
	  kill -KILL $$remaining 2>/dev/null || true; \
	fi; \
	if lsof -tiTCP:$(PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
	  echo "ERROR: port $(PORT) is still occupied."; \
	  exit 1; \
	fi; \
	[ -n "$(QUIET)" ] || echo "$(LABEL) stopped; port $(PORT) is free."
