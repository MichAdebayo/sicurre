# Sicurre

Phishing detection for French auto-entrepreneurs and TPEs. Inbound mail for a
protected domain arrives through Cloudflare Email Routing; an Email Worker calls
the Sicurre API, which classifies the message with a fine-tuned CamemBERTaV2
model and returns a verdict before the Worker forwards, quarantines or rejects.

This repository holds the data platform, the application and the API. The
model, its training pipeline and the ONNX inference service live in
[sicurre-ml](https://github.com/MichAdebayo/sicurre-ml).

> Earlier versions read mail through Gmail watches and moved phishing to Trash
> after delivery. That approach is superseded — see
> [ADR-0001](docs/adr/0001-cloudflare-email-routing-runtime.md) — and Gmail is no
> longer a runtime dependency.

## Install and run

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), Docker, and a
PostgreSQL database. `make help` lists every target; the ones below are the path
from a clean checkout to a running platform.

```bash
uv sync                      # install dependencies
cp .env.example .env         # then fill in the values
uv run alembic upgrade head  # create the schema
```

`.env.example` is the configuration reference: every variable the platform reads
is listed and commented there.

### Verify the checkout

```bash
make check                   # lint, types, and the full test suite
make test-unit               # unit tests alone, no database required
```

### Data platform

The platform runs in three stages, and each is a separate target so a failure
stops at a known point rather than half-way through a pipeline.

```bash
make ingest-all-base         # one-off: load the base corpora into raw records
make collect                 # recurring: pull the day's deltas from every source
make process                 # normalize, generate, annotate
make release                 # freeze a dataset version, export, publish
```

`make release` is idempotent by design: with no new eligible records it runs
normalization, generation and annotation, then exits without building a dataset
version. That is why it can be scheduled daily without producing a release a
day.

### Run the application

```bash
make dev-api                 # API alone
make dev                     # full stack via Docker Compose
make dev-stop                # tear it down
```

### Going further

| Document | Covers |
|----------|--------|
| [Development, CI and CD](docs/ops/development-setup.md) | Tooling versions, database setup, the five CI jobs, the delivery chain |
| [RGPD processing register](docs/data-platform/rgpd-register.md) | Purpose, legal basis, categories, retention and review procedures per source |
| [Logging and monitoring](docs/ops/logging-monitoring.md) | The metrics actually emitted, and which controls are declared but unverified |
| [deploy/README.md](deploy/README.md) | Production deployment |
| [docs/README.md](docs/README.md) | Documentation index |

## Navigate

| Folder | Contents |
|--------|----------|
| `docs/architecture/` | Goals, system design, data schema, NFRs, threat model, RGPD |
| `docs/adr/` | Architecture Decision Records — why we chose key options |
| `docs/api/` | OpenAPI contract + request/response examples |
| `docs/ops/` | Deployment, SLOs, monitoring, runbooks, incident templates |
| `docs/brand/` | Brand identity — colors, typography, motion, French UI copy rules |
| `docs/research/` | Competitive analysis, French corpus data sources, tech-stack survey |
| `tasks/` | Execution plan (`TASK_PLAN.md`) and agent lessons (`lessons.md`) |

## Conventions
- Diagrams: Mermaid embedded in Markdown
- ADRs: immutable records; append new ADRs rather than rewriting history
- Security & privacy: assume least privilege, encrypt sensitive data, minimize retention
- Visibility policy: see `docs/README.md`
