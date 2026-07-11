# Data Platform Test Layout

Tests under `tests/data_platform/` are grouped to scale by domain first, with a few explicit cross-cutting and test-type buckets:

- `api/` — backend API, schema, and auth-facing tests
- `certfr/` — CERT-FR extraction, review, and synthesis coverage
- `common_crawl/` — Common Crawl archive, ingestion, and promotion coverage
- `database/` — legacy DB, historical feed, and database-source routing coverage
- `file/` — file-based ingestion such as CSV loaders
- `normalization/` — text cleaning and normalization pipeline behavior
- `shared/` — cross-cutting shared services and stage-two utilities
- `sources/` — smaller source-specific tests that do not yet justify their own family folder
- `trace_schema/` — trace-emission contract tests kept together by test type

Guidelines:

- Keep new source-specific tests under their source family when a stable family exists.
- Put cross-cutting service tests under `shared/`.
- Keep trace-schema and similar contract-style suites together when the test type matters more than the source family.
- Prefer moving related tests into an existing family folder over adding a new top-level bucket for one file.