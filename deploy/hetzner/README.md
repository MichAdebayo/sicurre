# Hetzner Provisioning

Sicurre runs on a shared Hetzner host next to the Sicurre ML inference
service. The host-level `nginx-proxy` is the sole public HTTPS entry point;
this stack listens only on `127.0.0.1:8002`.

## One-Time Host Setup

Run these commands as a server administrator:

```bash
sudo useradd --create-home --shell /bin/bash sicurre-prod
sudo usermod -aG docker sicurre-prod
sudo -u sicurre-prod mkdir -p /home/sicurre-prod/sicurre/deploy
sudo -u sicurre-prod mkdir -p /home/sicurre-prod/.ssh
sudo chmod 700 /home/sicurre-prod/.ssh
sudo touch /home/sicurre-prod/.ssh/authorized_keys
sudo chmod 600 /home/sicurre-prod/.ssh/authorized_keys
```

Install the public half of the dedicated GitHub Actions deploy key in
`/home/sicurre-prod/.ssh/authorized_keys`. Generate the key locally with the
command in `deploy/DEPLOYMENT_BLOCKERS.md`; only its private half belongs in
GitHub Actions as `HETZNER_SSH_KEY`.

Seed the server-owned environment files once:

```bash
cd /home/sicurre-prod/sicurre
cp deploy/env.compose.example .env
cp deploy/env.api.example deploy/env.api
cp deploy/env.auth.example deploy/env.auth
chmod 600 .env deploy/env.api deploy/env.auth
```

Populate those files directly on the server. The CD workflow never uploads
runtime secrets and updates only `IMAGE_TAG` and `GHCR_OWNER` in `.env`.

Authenticate the `sicurre-prod` user to GHCR once with a GitHub PAT that has
`read:packages` access. This persistent server login is intentionally separate
from GitHub Actions' short-lived build token.

## Source-Specific Cron

Install `sicurre-crontab.example` as the `sicurre-prod` user after the first
successful deployment:

```bash
crontab /home/sicurre-prod/sicurre/deploy/hetzner/sicurre-crontab.example
crontab -l
```

Source entries start ephemeral tasks from the deployed API image, with the same
`deploy/env.api` configuration as the API service. The monthly publication uses
the dedicated `sicurre-data-release` image, which adds Kaggle tooling without
shipping it in the request-serving API. This keeps collection out of the API
process and preserves independent source cadences.

The monthly release runs on day three, after the monthly database and Common
Crawl jobs. Its preflight compares eligible records with the latest frozen
dataset and exits successfully without publishing when there is no growth.
When growth exists, it freezes and exports a new version, publishes it to
Kaggle, then dispatches the Sicurre ML repository.
