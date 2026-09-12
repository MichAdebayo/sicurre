# AGENTS.md — Sicurre

Read this before changing anything. It is short on purpose; the details live in
the documents it points to.

## What this is

Sicurre intercepts inbound mail for a protected domain through Cloudflare Email
Routing. An Email Worker posts the message to the Sicurre API, which classifies
it (rules, blocklists, a fine-tuned CamemBERTaV2 served by the sibling
`sicurre-ml` repository, and an optional LLM tier) and returns a verdict before
the Worker forwards, quarantines or rejects. The decision must fit a two-second
budget. Target users are French auto-entrepreneurs and TPEs with no IT team.

This repository holds the data platform, the API, the React application, the
Better Auth sidecar and the production deployment. The model, its training
pipeline and the ONNX inference service live in `sicurre-ml`.

| Path | Contents |
|------|----------|
| `src/data_platform/` | Ingestion, normalisation, dataset release; the FastAPI service and its routers |
| `src/app/` | React application (quarantine, threat journal, Domain Shield, settings) |
| `src/core/` | Shared runtime: config, database, inference client, metrics, alerting |
| `src/db/` | SQLAlchemy models and the two Alembic trees (`alembic.ini`, `alembic.app.ini`) |
| `src/poc/` | Streamlit proof of concept, kept as the incident sandbox for the certification |
| `auth-service/` | Better Auth sidecar (Node) |
| `deploy/` | Compose, Nginx, Alloy, Grafana dashboards and alert rules, cron |
| `tests/` | `unit`, `integration`, `e2e` |

## Commands

```bash
uv sync                          # Python dependencies
npm install                      # Node dependencies
make check                       # lint, types, full test suite
.venv/bin/ruff check src/ tests/ # Python lint
npx tsc --noEmit                 # TypeScript types
npx vitest run                   # front-end tests
.venv/bin/python -m pytest tests/unit -q
make openapi-check               # generated contract matches docs/api/openapi.yaml
make dev                         # full local stack (Docker Compose)
```

Before pushing, run the changed-line coverage gate that CI enforces:

```bash
mkdir -p coverage/python
.venv/bin/python -m pytest tests/unit tests/integration --cov=src --cov-branch \
  --cov-report=xml:coverage/python/coverage.xml -q
.venv/bin/diff-cover coverage/python/coverage.xml --compare-branch=origin/develop --fail-under=90
```

## Branches and delivery

`feature → app → develop → main`. Never push to `main`. CI gates `develop` and
`main`; CD deploys from `main` on CI success. The Docker app-stack smoke job runs
last and is the one that catches migration and boot failures; wait for it.

## Rules

- **French, plain, calm.** User-facing copy is French, sentence case, no em
  dashes, no uppercase styling. English is for code and developer docs.
- **Do not invent scope.** Build what was asked. Restructuring a surface whose
  purpose you have not understood is a regression, not an improvement.
- **Verify before claiming.** A statement about production, a test, or a file
  is checked before it is written down.
- **Database access goes through the API.** The Worker, the auth sidecar and
  the inference service hold no database credentials.
- **Every query on tenant tables filters on the workspace from the session**,
  never from request parameters. Every user-scoped endpoint has a test that
  requests another workspace's resource and expects 403 or 404.
- **Secrets stay in `.env` files on the host.** Provider tokens are stored
  encrypted (AES-256-GCM) and never returned or logged. Error responses carry no
  stack traces or internal state.
- **No raw e-mail bodies by default.** Quarantined MIME lives in R2 for 14
  days; logs and metrics carry no message content or personal identifiers.
- **New public endpoints get a rate limit** (ADR-0009).

## Code style

- Python 3.11+, typed, `async def` for handlers and I/O, `httpx.AsyncClient`,
  Pydantic v2 schemas, settings through `pydantic-settings`, no `os.environ` in
  business logic.
- Small functions, one responsibility per module, no god-files. `app_routes.py`
  and the setup route in `integrations.py`, under `src/data_platform/api/routers/`,
  are the debt, not the model.
- **Docstrings state the contract**: what it does, arguments, return, errors.
  Rationale goes to an ADR or the commit message; incident narrative goes to
  `docs/certification/incidents/`; measurements go to a dated report. A
  docstring never names a customer or describes a leaked secret.
- Front-end tokens come from `src/app/index.css` and `docs/brand/DESIGN.md`;
  no literal colours in components. Accessibility criteria are in
  `docs/architecture/accessibility.md`.

## Where to read next

- `docs/ops/development-setup.md` — tooling, database setup, CI jobs, delivery chain
- `docs/ops/deployment.md` and `deploy/README.md` — production
- `docs/architecture/` — system context, data design, threat model, monitoring
- `docs/adr/` — why the current options were chosen; superseded ADRs stay for history
- `docs/api/openapi.yaml` — the API contract
- `PRODUCT.md` and `docs/brand/` — audience, tone, design system
