# Issue Artifact

## Issue #1 — Bloc 1 source perimeter

Status: done

### Frozen sources

| Source | Type | Status |
|--------|------|--------|
| PhishTank | API REST | frozen |
| CERT-FR CTI reports | scraping | frozen |
| AFI / antifraudintl French corpus | scraping | frozen |
| Local CSV/TXT corpora | file | frozen |
| SQLite/PostgreSQL read-back extraction | SQL database | frozen |
| BigQuery | big data | frozen |
| Common Crawl | big data | frozen |

### Secondary in-scope sources

| Source | Type | Status |
|--------|------|--------|
| Synthetic French corpus | Faker | secondary |
| Adapted EN to FR corpus | file | secondary |

### Not frozen

| Source class | Status |
|-------------|--------|
| additional phishing feeds | candidate |
| additional scraping targets without extraction evidence | candidate |
| additional corpora outside current platform flow | candidate |

### Excluded from Bloc 1 perimeter

| Source | Reason |
|--------|--------|
| live Gmail mailbox ingestion | runtime flow, not Bloc 1 perimeter |
| live M365 tenant ingestion | runtime flow, not Bloc 1 perimeter |
| runtime telemetry and app logs as training data | monitoring and feedback scope |
| ad hoc manual uploads outside defined ingestion flow | not stable perimeter evidence |

### Related docs

- `docs/architecture/component-design.md`
- `docs/architecture/data-design.md`
- `tasks/TASK_PLAN.md`

## Issue #2 — Shared ingestion contract

Status: done

### Resolution note

- The shared ingestion contract is documented in `docs/architecture/component-design.md`
- The contract applies to API, file, scraping, SQL, and big data sources
- Required metadata is explicitly defined for ingestion runs and raw objects
- The distinction between raw object and raw record is explicitly stated
- The contract is aligned to `data_source_system`, `data_ingestion_run`, `data_raw_object`, and `data_raw_record` in `docs/architecture/data-design.md`

### Related docs

- `docs/architecture/component-design.md`
- `docs/architecture/data-design.md`
- `docs/api/openapi.yaml`

## Issue #3 — Bloc 1 SQL schema and migration baseline

Status: done

### Resolution note

- The Bloc 1 physical schema now exists as executable SQLAlchemy models and an Alembic baseline migration
- The canonical PostgreSQL reference DDL is versioned in `sql/sicurre.sql`
- The same logical schema is validated on SQLite for dev and CI through the backend test suite
- The baseline was exercised through ORM schema creation and Alembic migration execution before route work continued

### Evidence

- `src/db/models/lineage.py`
- `src/db/migrations/versions/20260306_0001_bloc1_baseline.py`
- `alembic.ini`
- `src/db/sql/sicurre.sql`
- `tests/data_platform/api/test_bloc1_schema.py`

## Issue — Traceability persistence for source systems and ingestion runs

Status: done

### Resolution note

- `data_source_system` and `data_ingestion_run` now have executable SQLAlchemy models and an Alembic baseline in the backend codebase
- The one-to-many linkage is implemented through `data_ingestion_run.source_system_id -> data_source_system.id`
- `/v1/data/sources` and `/v1/data/ingestion-runs` are implemented in the FastAPI backend and aligned with `docs/api/openapi.yaml`
- API-level tests validate source creation/listing, ingestion run creation/listing, and rejection of ingestion runs referencing a missing source system

### Evidence

- `src/db/models/lineage.py`
- `src/data_platform/api/routers/source_systems.py`
- `src/data_platform/api/routers/ingestion_runs.py`
- `src/db/migrations/versions/20260306_0001_bloc1_baseline.py`
- `tests/data_platform/api/test_lineage_api.py`

## Issue #13 — Bloc 0 notebook classification

Status: done

### Classification note

- Notebook families are explicitly grouped under `notebooks/api`, `notebooks/bigdata`, `notebooks/csv`, `notebooks/db`, `notebooks/ml`, `notebooks/processing`, and `notebooks/scraping`
- Repository data lineage already maps key notebook outputs to `data/raw`, `data/processed`, and `data/final`
- Active migration direction is clear: notebooks remain as exploratory or evidence artifacts, while reusable logic is being moved into scripts and shared pipelines

### Evidence

- `data/README.md`
- `notebooks/`

## Issue #25 — SQL evidence, import procedure, and execution steps

Status: done

### Resolution note

- The canonical PostgreSQL evidence is versioned in `sql/sicurre.sql`
- The executable migration baseline remains `20260306_0001_bloc1_baseline.py`
- A dedicated runbook now documents the dev SQLite path, the preferred PostgreSQL Alembic path, and the manual PostgreSQL import path
- The runbook includes the exact commands used to execute the baseline and validate it with the Bloc 1 backend test suite

### Evidence

- `docs/ops/bloc1-sql-runbook.md`
- `src/db/sql/sicurre.sql`
- `alembic.ini`
- `src/db/migrations/versions/20260306_0001_bloc1_baseline.py`
- `tests/data_platform/api/test_bloc1_schema.py`

## Issue #38 — Clarify recurring ingestion architecture and source cadence

Status: done

### Resolution note

- Bloc 1 architecture now states that automation means recurring, sustainable collection rather than synthetic data volume.
- The frozen primary recurring-source matrix is documented with source-specific cadence.
- Cadence is justified by source behavior, so weekly and batch-based jobs remain valid recurring evidence.
- Candidate secondary scraping sources, including Reddit, are explicitly separated from the frozen primary perimeter.

### Evidence

- `docs/architecture/component-design.md`
- `docs/architecture/backend-plan.md`
- `tasks/bloc1-automation-issues.md`

## Issue #39 — Document ingestion trigger semantics in data design and API contract

Status: done

### Resolution note

- `trigger_mode` semantics are documented in the data design as `manual` and `scheduled`.
- The OpenAPI contract now exposes the same two values for ingestion run creation.
- The documentation explicitly states that this is a contract clarification for recurring lineage and not a schema redesign.

### Evidence

- `docs/architecture/data-design.md`
- `docs/api/openapi.yaml`
- `tasks/bloc1-automation-issues.md`

## Issue #40 — Define CERT-FR automated collection strategy and filtering rules

Status: done

### Resolution note

- The recurring CERT-FR strategy now defines `actualite`, `alerte`, and optional `avis` as the collection entry points.
- Weekly cadence is documented as the default because CERT-FR is relevant but not a high-frequency feed.
- Relevance filtering is required before detailed extraction or attachment handling.
- The first version explicitly prefers HTML or JSON index polling and rejects browser-automation-first designs.

### Evidence

- `docs/architecture/component-design.md`
- `docs/architecture/backend-plan.md`
- `tasks/bloc1-automation-issues.md`