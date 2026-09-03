# Bloc 1 SQL Baseline Runbook

Purpose: provide operational and certification evidence for the current Bloc 1
data-platform SQL baseline.

## Scope

This runbook covers the data-platform schema implemented in
`src/db/models/lineage.py`, including:

- ingestion lineage tables
- normalized-message and annotation tables
- dataset build/export/publish tables
- generation lineage tables
- `pipeline_state`
- `poc_user` for the Streamlit POC

Product runtime app tables are outside this runbook.

## Authoritative Evidence

The current baseline is represented in three layers:

- Architecture source of truth: `docs/architecture/data-design.md`
- Executable implementation: `src/db/models/lineage.py`
- Alembic baseline: `src/db/migrations/versions/20260708_0001_current_baseline.py`
- PostgreSQL reference DDL: `src/db/sql/sicurre.sql`

The older exploratory migration chain has been retired because the data
platform database is not yet in production and can be rebuilt cleanly.

## Environment Assumptions

- Python version: 3.11+
- Package manager: `uv`
- Env file: `.env`
- Data-platform dev DB: `SICURRE_DATA_PLATFORM_DATABASE_URL`
- Typical local DB path: `data/local/sicurre_dataplatform.db`

## Recreate the Local SQLite Baseline

The safe local rebuild command is:

```bash
make poc-replay-frozen
```

That target:

1. refuses to reset a non-SQLite database
2. deletes the configured local SQLite data-platform DB
3. runs `uv run alembic upgrade head`
4. runs normalization and annotation maintenance
5. seeds the `current_frozen` dataset lineage for the POC

For schema-only validation:

```bash
uv run alembic upgrade head
```

## PostgreSQL Path

Preferred production path:

```bash
uv run alembic upgrade head
```

Manual audit path:

```bash
psql "$POSTGRES_URL" -f src/db/sql/sicurre.sql
```

Use the SQL file for review/audit. Use Alembic for normal application-managed
schema creation.

## Validation Commands

Focused validation for the current schema pass:

```bash
uv run pytest \
  tests/integration/data_platform/sources/test_sekoia_ioc.py \
  tests/integration/data_platform/shared/test_sqlite_uuid_queries.py \
  tests/integration/data_platform/shared/test_dataset_publish_service.py \
  tests/integration/data_platform/api/test_dataset_publish.py \
  tests/integration/data_platform/api/test_bloc1_schema.py \
  -q
```

Full data-platform suite:

```bash
uv run pytest tests/unit tests/integration -q
```

## Cadence and Publishing

Source-specific cron jobs collect raw data at different cadences. Monthly
training publication is a separate release job that freezes a dataset, exports
train/val/test files, pushes a Kaggle version, and dispatches the ML repository
training workflow.

See `docs/architecture/data-platform-cadence.md`.

## Evidence Checklist

Issue 25 is complete when all of the following are true:

1. `src/db/sql/sicurre.sql` exists as PostgreSQL evidence.
2. `20260708_0001_current_baseline.py` exists as the executable baseline.
3. local SQLite schema creation is documented.
4. PostgreSQL import/review is documented.
5. data-platform tests validate the schema and core workflows.

## Related Documents

- `docs/architecture/data-design.md`
- `docs/architecture/data-platform-cadence.md`
- `docs/architecture/backend-plan.md`
- `docs/architecture/issue-artifact.md`
- `docs/api/openapi.yaml`
- `src/db/sql/sicurre.sql`
