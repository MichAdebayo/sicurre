# Deploy

This folder is reserved for host/server provisioning and runtime configuration.
Application container build files and production orchestration live at the
repository root.

## Runtime Layout

The main production stack is owned by the dedicated Linux user `sicurre-prod`:

```text
/home/sicurre-prod/sicurre/
  docker-compose.prod.yml
  deploy/env.prod
  deploy/nginx/
  deploy/alloy/
```

The production compose file starts:

- `sicurre-app`: built React app plus same-origin proxy, bound to `127.0.0.1:8002`
- `sicurre-api`: FastAPI/data-platform runtime
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
HETZNER_HOST=77.42.67.255
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

The CD workflow updates only `IMAGE_TAG` and `GHCR_OWNER` in `.env`.
Application/provider secrets remain server-managed.

## Start

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --remove-orphans
```

Observability is optional while Grafana is unavailable:

```bash
docker compose --profile observability -f docker-compose.prod.yml up -d alloy
```

See `deploy/nginx/README.md` for the shared reverse proxy setup and
`deploy/alloy/README.md` for log forwarding. See `deploy/grafana/README.md`
for dashboard provisioning notes and the separation between runtime
observability and app-level admin analytics.
