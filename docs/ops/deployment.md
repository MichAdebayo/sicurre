# Deployment

How the application reaches production and what runs there. The step-by-step
host bootstrap (Linux user, deploy key, GHCR login, environment files) is in
`deploy/README.md` and `deploy/hetzner/README.md`.

## Environments

| Environment | What it is | Database |
|-------------|------------|----------|
| Local | `make dev` (Docker Compose) or `make dev-api` plus `npm run dev` | SQLite under `data/local/` |
| CI | GitHub Actions on every push and pull request; the Docker app-stack smoke job boots the full stack | SQLite in the job |
| Production | One Hetzner VPS in the EU, Docker Compose, Nginx as the public entry point, Cloudflare in front | Neon PostgreSQL (pooled endpoint, `sslmode=verify-full`) |

There is no staging environment. Changes are proven by CI and by the smoke
job, then deployed by CD from `main`.

## Services in production (`docker-compose.prod.yml`)

| Service | Role | Exposure |
|---------|------|----------|
| `sicurre-app` | Built React application plus its same-origin proxy | `127.0.0.1:8002`, behind Nginx |
| `sicurre-api` | FastAPI: application routes, data-platform routes, the Worker's scan endpoint | Internal, proxied by `sicurre-app` |
| `auth-service` | Better Auth sidecar (Node) | Internal, `127.0.0.1:3005` |
| `sicurre-data-release` | Monthly dataset freeze, export and Kaggle publication; profile-gated, not long-lived | None |
| `alloy` | Grafana Alloy: Docker logs, Prometheus scrapes, OTLP traces to Grafana Cloud | Internal |
| `node-exporter`, `cadvisor` | Host and container metrics for the infrastructure dashboard | Internal |

The inference service is not part of this stack. It is deployed by the sibling
`sicurre-ml` repository and reached at `SICURRE_INFERENCE_API_URL`
(`https://api.sicurre.com/v1/classify`). Inbound mail arrives through
Cloudflare Email Routing and the Email Worker provisioned per customer domain.

## Configuration and secrets

Configuration is split by container so that no service receives secrets it
does not use. All files live on the host under the deploy path and are never
written by CD:

| File | Holds |
|------|-------|
| `.env` | Compose interpolation only: image tag, GHCR owner, host port. CD updates `IMAGE_TAG` and `GHCR_OWNER` here |
| `deploy/env.api` | Database URLs, Cloudflare and R2 credentials, inference URL and key, internal API key, Loops |
| `deploy/env.auth` | Better Auth secret and database URL, Turnstile keys, verification e-mail sender |
| `deploy/env.alloy` | Grafana Cloud ingestion credentials (Prometheus, Loki, OTLP) |

The `*.example` versions of each file under `deploy/` list every variable and
are checked in CI. GitHub Actions holds only the four values CD needs to reach
the host (`HETZNER_HOST`, `HETZNER_USER`, `HETZNER_SSH_KEY`, `DEPLOY_PATH`) plus
the Grafana provisioning token.

Customer Cloudflare tokens are stored encrypted (AES-256-GCM) in the database;
the key is mandatory in production and the API refuses to start without it.

## Delivery chain

```
feature  →  app  →  develop  →  main
                      CI          CI, then CD
```

- **CI** (`.github/workflows/ci.yml`) runs on every push and pull request:
  workflow lint, secret scan, Node audit and build, Better Auth typecheck,
  Vitest, Python lint and types, docstring gate, OpenAPI contract check,
  pytest with the coverage ratchet and the 90 % changed-line gate, then the
  Docker app-stack smoke job. A red job blocks the merge.
- **CD** (`.github/workflows/cd.yml`) runs on a successful CI run on `main`, or
  by manual dispatch with an image tag. It derives the tag, builds and pushes
  four images to GHCR (`sicurre-app`, `sicurre-auth`, `sicurre-api`,
  `sicurre-data-release`), copies the Compose file and configuration to the
  host, pulls and recreates the stack, polls the gateway and the API up to
  thirty times, then provisions the Grafana dashboards and alert rules.
- **Migrations** run at API start: `alembic upgrade head` for the data
  platform, then `alembic -c alembic.app.ini upgrade head` for the
  application. Uvicorn starts only if both succeed. Better Auth migrates its
  own `auth` schema when the sidecar starts.

## Rollback

Every deployment is a set of immutable images tagged by version or commit.
Rolling back is one manual CD dispatch (Actions, "CD", "Run workflow") with
the previous tag in `image_tag`. On a dispatch that names a tag the build job
is skipped, the deploy job first checks that the four images exist in GHCR
under that tag and fails before touching the host if one is missing, then
writes `IMAGE_TAG` on the host, pulls the images and recreates the containers.
The health check that follows is the same as for any deployment. The
procedure was exercised on 18 July 2026 (v1.4.2 to v1.4.1 and back), see
`docs/certification/incidents/`, and the workflow path was proven on
12 September 2026 with a same-tag dispatch of v1.33.3.

## After a deployment

- `GET /health` answers on the API; `GET /health/ready` also checks the
  database.
- The Grafana "Sicurre runtime overview" dashboard shows the new image tag
  and request traffic within a minute.
- `docs/ops/runbooks.md` covers what to do when either does not happen.
