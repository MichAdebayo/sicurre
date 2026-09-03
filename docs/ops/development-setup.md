# Development environment, CI and CD

Setup, verification and delivery for the Sicurre platform. The model and its
inference service live in the companion `sicurre-ml` repository and have their
own equivalent.

## Prerequisites

| Tool | Version | Why |
|------|---------|-----|
| Python | 3.11+ | `pyproject.toml` requires it |
| [uv](https://docs.astral.sh/uv/) | current | Dependency resolution and the runner; every command below assumes it |
| Node | 20+ | Frontend build and the app gateway |
| Docker + Compose | current | Local stack and the production images |
| PostgreSQL | 15+ | Two databases, application and data platform |

## Install

```bash
uv sync
```

```bash
cp .env.example .env
```

`.env.example` is the configuration reference — every variable the platform
reads is listed and commented there. Two connection strings are required and
are deliberately separate:

- `SICURRE_DATABASE_URL` — the application: quarantine, events, feedback
- `SICURRE_DATA_PLATFORM_DATABASE_URL` — the training corpus

Keeping them apart is what lets customer email and corpus records have different
retention and different governance. See the
[RGPD register](../data-platform/rgpd-register.md).

```bash
uv run alembic upgrade head
```

## Verify the checkout

```bash
make check
```

Lint, types and the full suite. For a faster loop, `make test-unit` needs no
database.

```bash
npm install && npm test
```

The frontend and gateway tests are separate; `make check` does not run them.

## Run it

```bash
make dev-api        # API alone, hot reload
make dev            # full stack under Compose
make dev-stop       # tear down
```

With the API running, `http://127.0.0.1:8000/docs` serves Swagger UI and
`/redoc` serves ReDoc. In production both are proxied through the app gateway,
which forwards `/docs`, `/redoc`, `/openapi.json` and the API paths and hands
everything else to the single-page application.

## Data platform

Three stages, each its own target so a failure stops at a known point rather
than part-way through a pipeline.

```bash
make ingest-all-base   # one-off: load the base corpora
make collect           # recurring: the day's deltas from every source
make process           # normalize, generate, annotate
make release           # freeze, export, publish
```

`make release` is idempotent by design. With no new eligible records it runs
normalization, generation and annotation, then exits without building a version
— which is why it can be scheduled daily without producing a release a day.

`make help` lists every target.

## Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request. Five independent
jobs, so one failure does not mask the others:

| Job | Checks |
|-----|--------|
| **Workflow syntax** | `actionlint` over the workflow files |
| **Secret scan** | Repository scanned for committed credentials |
| **App audit, build, and auth typecheck** | Node tests with coverage, production dependency audit, frontend build, Better Auth sidecar typecheck |
| **Data-platform quality and tests** | Lint, types, the Python suite, and the coverage gate |
| **Docker app-stack smoke** | The Compose stack is built and exercised |

The coverage gate applies to changed lines rather than the whole tree, so a
change is measured against itself.

### Running CI locally

```bash
make check                                     # data-platform job
npm test && npm run build                      # app job
uv run python .github/scripts/scan_secrets.py  # secret scan
make app-stack-smoke                           # docker smoke
```

`actionlint` needs the binary; CI installs it.

## Continuous delivery

`.github/workflows/cd.yml` runs when CI completes successfully **on `main`**, and
never directly on a push.

1. **Version release** — semantic release resolves the version and image tags
2. **Build and push images** — app gateway, auth sidecar, API/data platform, to GHCR
3. **Deploy** — images pulled on the host and the stack restarted
4. **Validate** — the deployment is exercised before the change is accepted

Branches promote `feature → app → develop → main`. Nothing is pushed to `main`
directly; CD is the only thing that reaches production.

### Configuration on the host

The production `.env` lives on the server and is not in the repository.
`.env.example` documents every key. Values that change behaviour rather than
credentials — timeouts, rate limits, the SLA threshold — are worth reviewing
against it after a deploy, since an unset variable silently takes a code default
that may predate the current objective.

## Scheduled work

`deploy/hetzner/sicurre-crontab.example` is the source of the production
schedule: ingestion staggered through the early morning, weekly scraping,
monthly database and Common Crawl work, and the dataset release. The release is
temporarily daily until the defence and reverts to monthly on the 3rd
afterwards; the file carries that instruction inline.
