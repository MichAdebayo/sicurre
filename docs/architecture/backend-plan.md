# Backend architecture plan

## Purpose

This document defines the target backend organization before implementation.
It translates the certification-first architecture into a codebase structure that can evolve from experimental notebooks into a maintainable platform.

The goal is to avoid starting from a product-only SaaS backend and instead build the data platform backbone first.

## Guiding principle

Use one backend codebase with three internal domains:

- data platform domain for Bloc 1
- model runtime domain for Bloc 2
- application domain for Bloc 3

This is a modular monolith strategy.
It is simpler to implement, easier to defend during the certification, and still compatible with later service extraction.

The delivery roadmap is broader than the runtime domain split.
Execution now follows Bloc 0 plus 5 delivery blocs:

- Bloc 0: baseline and governance
- Bloc 1: data platform
- Bloc 2: technical survey and proof of concept
- Bloc 3: model
- Bloc 4: app
- Bloc 5: monitoring

The survey bloc produces benchmark and feasibility evidence.
The monitoring bloc is implemented as a cross-cutting capability rather than as a separate business domain.

## Frozen naming convention

The backend and database must use explicit domain prefixes.

- `data_` for data platform tables and related artifacts
- `ml_` for model lifecycle tables and related artifacts
- `app_` for application runtime tables and related artifacts

This convention is now frozen for the reorganization phase.
It improves readability, makes SQL ownership obvious, and prevents Bloc 1 tables from being confused with SaaS runtime tables.

## Target codebase structure

```text
src/
  core/              # Configuration, security, DB connections
  db/                # Consolidated database layer
    models/          # SQLModel/SQLAlchemy entities
    queries/         # Repository/Query logic
    services/        # DB-heavy business services
    migrations/      # Alembic environment
    sql/             # Physical SQL schemas/DDL
  data_platform/     # Specific data domain
    api/             # Data ingestion/curation API
    extractors/      # Source-specific connectors
    cleaning/        # Normalization logic
    services/        # Domain services (adaptation, snapshot)
    cron_schedulers/ # Periodic ingestion triggers
  app/               # (Future) User-facing application domain

scripts/             # Operational scripts (monorepo root)
  data_platform/
  app/

notebooks/           # Exploratory work (monorepo root)
  data_platform/
  app/

data/
  local/             # Local SQLite (sicurre.db) and SQL exports
  raw/               # Raw snapshots (API/Scraping)
  processed/         # Cleaned/Normalized records
```

## Domain responsibilities

### Survey and proof-of-concept work

Does not require a dedicated runtime domain.

Its outputs are:

- benchmark and recommendation documents
- proof-of-concept experiments
- feasibility decisions that reduce implementation risk before major coding work

The main repository anchor for this bloc is the research and architecture documentation rather than backend runtime code.

### Data platform domain

Owns:

- source registry
- ingestion run tracking
- raw object and raw record lineage
- normalization results
- annotations
- dataset versioning and split membership
- data API endpoints

For Bloc 1 automation evidence, this domain also owns the recurring ingestion intent:

- scheduled execution of source connectors
- registration of each recurring execution as an ingestion run
- source-specific cadence decisions
- filtering and parsing of newly collected payloads before normalization

This domain is the first implementation priority.

### Bloc 1 automation slice

The first automation slice should remain intentionally small.

Target scope:

- one minimal scheduler or externally triggered recurring job mechanism
- one daily API source job (PhishTank)
- one weekly scraping source job (CERT-FR)
- weekly or batch jobs for big data, SQL, and file refresh paths

The purpose is to prove recurring collection, not to build a full orchestration platform.

Recommended implementation style:

- external scheduler or cron-triggered scripts
- ingestion code remains in the Bloc 1 data platform boundary
- each execution writes a `data_ingestion_run` row with a documented trigger mode

Deferred scope:

- no workflow engine requirement at this stage
- no browser-automation-first design for CERT-FR
- no schema redesign for candidate secondary sources such as Reddit

### Model runtime domain

Owns:

- model inference contracts
- classifier request and response schemas
- model metadata exposure
- evaluation and runtime monitoring interfaces

This domain reads curated datasets from the data platform but does not own their lifecycle.

### Application domain

Owns:

- user-facing product concerns
- Better Auth session integration
- threat log
- Cloudflare Email Routing integration
- quarantine and remediation actions
- feedback for deployed product usage
- dashboard-facing endpoints

This domain is downstream from the data platform and classifier layers.

### Observability capability

Owns:

- metrics instrumentation
- structured logging filters
- alert definitions
- incident response evidence

This capability spans all domains and is the technical backbone of the monitoring delivery bloc.

## Table groups

### Data platform tables

- `data_source_system`
- `data_ingestion_run`
- `data_raw_object`
- `data_raw_record`
- `data_processing_run`
- `data_normalized_message`
- `data_annotation`
- `data_dataset`
- `data_dataset_item`

### Model and MLOps tables

- `ml_model_version`
- `ml_model_evaluation`
- `ml_model_deployment`

### Application tables

- Better Auth library tables: `user`, `session`, `account`, `verification`
- `app_workspace`
- `app_workspace_membership`
- `cloudflare_integration`
- `app_cloudflare_config`
- `app_inference_event`
- `app_quarantine_item`
- `app_alert_preference`
- `app_alert_history`
- `app_security_rule`
- `app_domain_shield_status`
- `app_domain_shield_history`
- `app_feedback`

## Recommended implementation order

### Step 0

Complete the survey and proof-of-concept evidence needed to lock the implementation path:

- stack comparison
- proof-of-concept conclusions
- accepted and rejected options

### Step 1

Implement the data platform domain first:

- relational schema
- migrations
- queries layer (formerly repositories)
- data API contracts
- recurring-ingestion planning and trigger semantics

### Step 2

Implement dataset export and read endpoints used by training and evaluation.

### Step 3

Implement the classifier API and model metadata contracts.

### Step 4

Implement the application domain and runtime product features.

### Step 5

Instrument monitoring and incident-response evidence across the data, model, and application layers.

## API segmentation

The backend should expose three API surfaces under one codebase:

- `/v1/data/...` for Bloc 1
- `/v1/model/...` for Bloc 2
- `/v1/threats`, `/v1/quarantine`, `/v1/feedback`, `/v1/alerts/...`, `/v1/domain-shield/...`, and `/v1/integrations/cloudflare/...` for Bloc 3 runtime product flows
- `/api/auth/...` for Better Auth sidecar routes exposed through the frontend/API proxy

This keeps the certification narrative explicit and avoids mixing data CRUD with end-user SaaS behavior.

## Why this is the right backbone

- it aligns the codebase structure with the certification blocks
- it preserves the experimental work already done in notebooks and scripts
- it supports a clean migration path from CSV exploration to SQL-backed APIs
- it prevents the runtime SaaS model from dominating the architecture too early
