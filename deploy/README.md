# Deploy

This folder is reserved for host/server provisioning and runtime configuration.
Application container build files and production orchestration live at the
repository root.

## Runtime Layout

The main production stack is owned by the dedicated Linux user `sicurre-prod`:

```text
/home/sicurre-prod/sicurre/
  docker-compose.prod.yml
  .env
  deploy/env.api
  deploy/env.auth
  deploy/env.alloy
  deploy/nginx/
  deploy/alloy/
```

The production compose file starts:

- `sicurre-app`: built React app plus same-origin proxy, bound to `127.0.0.1:8002`
- `sicurre-api`: FastAPI/data-platform runtime
- `sicurre-data-release`: profile-gated monthly Kaggle publication runner
- `auth-service`: Better Auth sidecar
- `alloy`: Grafana Alloy collector for app logs and app gateway metrics

The ML inference API is deployed by the sibling `sicurre-ml` repository and is
reached through `SICURRE_INFERENCE_API_URL` (currently `https://api.sicurre.com/v1/classify`).
Nginx is shared host infrastructure and proxies public HTTPS traffic to the app
loopback port.

## First Server Bootstrap

Create the isolated deployment user:

```bash
sudo useradd --create-home --shell /bin/bash sicurre-prod
sudo usermod -aG docker sicurre-prod
```

Seed SSH access for GitHub Actions:

```bash
sudo -u sicurre-prod mkdir -p /home/sicurre-prod/.ssh
sudo -u sicurre-prod chmod 700 /home/sicurre-prod/.ssh
sudo -u sicurre-prod touch /home/sicurre-prod/.ssh/authorized_keys
sudo -u sicurre-prod chmod 600 /home/sicurre-prod/.ssh/authorized_keys
```

GitHub repository secrets expected by CD:

```text
HETZNER_HOST=<server public IP or hostname>
HETZNER_USER=sicurre-prod
HETZNER_SSH_KEY=<private deploy key>
DEPLOY_PATH=/home/sicurre-prod/sicurre
```

Log in to GHCR once on the server as `sicurre-prod`:

```bash
echo "<GHCR_READ_PACKAGES_PAT>" | docker login ghcr.io -u "<github-user>" --password-stdin
```

## Production Environment

Production env is split by container boundary. This avoids injecting every
secret into every container.

The API uses two explicit databases: `SICURRE_DATABASE_URL` owns product/app
tables and `SICURRE_DATA_PLATFORM_DATABASE_URL` owns lineage and dataset
tables. Better Auth uses the same app database through
`SICURRE_BETTER_AUTH_DATABASE_URL`, but owns only the dedicated `auth` schema.
Production should use Neon's pooled hostname (the endpoint containing
`-pooler`) with `sslmode=verify-full`. The auth service scopes Better Auth's
Kysely queries to the `auth` schema because Neon rejects `search_path` as a
pooled startup option.
Its URL must use Neon's direct host because the pooled endpoint rejects the
session `search_path` needed for schema isolation.

```text
.env                 # Compose interpolation only; image tag, GHCR owner, host port.
deploy/env.api       # FastAPI/data-platform secrets and source credentials.
deploy/env.auth      # Better Auth sidecar and auth email secrets.
deploy/env.alloy     # Grafana/Alloy credentials; only needed with observability profile.
```

Seed the files on the server:

```bash
cp deploy/env.compose.example .env
cp deploy/env.api.example deploy/env.api
cp deploy/env.auth.example deploy/env.auth
cp deploy/env.alloy.example deploy/env.alloy
chmod 600 .env deploy/env.api deploy/env.auth deploy/env.alloy
```

`deploy/env.api` must define `SICURRE_INTERNAL_API_KEY` for authenticated
Sicurre-ML provenance callbacks. Store the identical value in the Sicurre-ML
GitHub Actions secret named `SICURRE_INTERNAL_API_KEY`; do not reuse the ML
inference bearer token.

The CD workflow updates only `IMAGE_TAG` and `GHCR_OWNER` in `.env`.
Application/provider secrets remain server-managed.

`SICURRE_REPORT_EMAIL` is a non-secret GitHub Actions repository or `production`
environment variable. CD passes it to the frontend image as the build-time Vite
variable `VITE_SICURRE_REPORT_EMAIL`. Do not place the Vite variable in
`deploy/env.api`: that file is loaded by the Python container after the frontend
bundle has already been built.

Apply both Python-owned schemas before first start with `alembic upgrade head`
and `alembic -c alembic.app.ini upgrade head`. The production API startup runs
both idempotently. Better Auth applies its own schema migration when the
sidecar starts; `npm run auth:migrate` is the explicit operator command.

The Better Auth sidecar also supports an idempotent initial owner seed through
`SICURRE_ADMIN_EMAIL`, `SICURRE_ADMIN_PASSWORD`, and `SICURRE_ADMIN_NAME` in
`deploy/env.auth`. Configure all three or none. On startup, a missing account is
created and verified before the HTTP listener opens; an existing account keeps
its password while its safe profile fields are normalized. Platform access is
still granted only when the same email is present in
`SICURRE_PLATFORM_ADMIN_EMAILS` for the API container.

## Start

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --remove-orphans
```

The scheduled dataset release uses the optional `release` profile and does not
run as a long-lived service:

```bash
docker compose --profile release -f docker-compose.prod.yml run --rm --no-deps sicurre-data-release
```

Alloy starts with the production stack and exports all meaningful API request
traces. Health, metrics, and documentation probes are excluded, and duplicate
HTTP access logs are disabled. Sampling remains configurable through
`SICURRE_TELEMETRY_TRACE_SAMPLE_RATIO` if production traffic later approaches
the Grafana Free ingestion allowance.

```bash
docker compose -f docker-compose.prod.yml up -d alloy
```

See `deploy/nginx/README.md` for the shared reverse proxy setup and
`deploy/alloy/README.md` for log forwarding. See `deploy/grafana/README.md`
for dashboard provisioning notes and the separation between runtime
observability and app-level admin analytics.

`deploy/hetzner/README.md` contains the dedicated-user, SSH-key, and
source-specific cron installation steps. `deploy/DEPLOYMENT_BLOCKERS.md` is
the exact GitHub-secret and external-service checklist for first deployment.
