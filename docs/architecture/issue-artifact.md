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

## Issue #13 — Bloc 0 notebook classification

Status: done

### Classification note

- Notebook families are explicitly grouped under `notebooks/api`, `notebooks/bigdata`, `notebooks/csv`, `notebooks/db`, `notebooks/ml`, `notebooks/processing`, and `notebooks/scraping`
- Repository data lineage already maps key notebook outputs to `data/raw`, `data/processed`, and `data/final`
- Active migration direction is clear: notebooks remain as exploratory or evidence artifacts, while reusable logic is being moved into scripts and shared pipelines

### Evidence

- `data/README.md`
- `notebooks/`