# Test Layout

Tests are classified by boundary first and ownership second:

```text
tests/
  unit/
    app/
    data_platform/
  integration/
    app/
    data_platform/
  e2e/
    app/
    data_platform/
```

- `unit/`: deterministic tests of one function, class, or configuration unit;
  no database, network client, running service, or provider boundary.
- `integration/`: tests involving API applications, SQLite/SQLAlchemy, files,
  storage adapters, or mocked HTTP/provider contracts.
- `e2e/`: live or containerized workflows spanning deployable components.
  These require explicit commands and are excluded from default pytest discovery.

Within `app/` and `data_platform/`, preserve stable domain families such as
`api`, `common_crawl`, `normalization`, `sources`, and `shared`.

Commands:

```bash
make test-unit
make test-integration
make app-stack-smoke
make data-platform-staging-smoke
make poc-inference-smoke
make poc-ui-smoke
```
