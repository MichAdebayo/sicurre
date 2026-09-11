# Deployment Prerequisites

This is the one-time checklist for deploying the Sicurre application stack.
No production secret belongs in Git, Docker images, or the CD artifact upload.

## GitHub Actions Secrets

Add these repository-level Actions secrets:

| Secret | Value | Status |
| --- | --- | --- |
| `HETZNER_HOST` | Hetzner server hostname or IP | required |
| `HETZNER_USER` | `sicurre-prod` | required |
| `HETZNER_SSH_KEY` | private half of the dedicated deploy key | required |
| `DEPLOY_PATH` | `/home/sicurre-prod/sicurre` | required |

No database, Cloudflare, R2, Kaggle, Better Auth, Loops, Grafana, or inference
secret is needed in GitHub Actions. Those values remain in the server's split
environment files.

Generate the dedicated deploy key on the local machine:

```bash
ssh-keygen -t ed25519 -C "github-actions-sicurre-deploy" \
  -f ~/.ssh/sicurre_deploy_key -N ""
```

Put `~/.ssh/sicurre_deploy_key.pub` in `sicurre-prod`'s `authorized_keys`; put
the private file's content in `HETZNER_SSH_KEY`. Never place either key in this
repository.

## Server-Owned Runtime Files

Before the first CD run, create and populate:

```text
/home/sicurre-prod/sicurre/.env
/home/sicurre-prod/sicurre/deploy/env.api
/home/sicurre-prod/sicurre/deploy/env.auth
```

Optional after Grafana Cloud is available:

```text
/home/sicurre-prod/sicurre/deploy/env.alloy
```

`deploy/env.api` must use `SICURRE_INFERENCE_API_URL=https://api.sicurre.com/v1/classify`
and its matching internal key. The inference container is owned by the sibling
`sicurre-ml` deployment and must not be started by this Compose stack.

## Cloudflare and TLS

- `sicurre.com` DNS must route through Cloudflare to the Hetzner server.
- Create a Sicurre-zone Origin CA certificate for `sicurre.com` and
  `*.sicurre.com`.
- Install it under `/opt/nginx-proxy/ssl/` using the exact names referenced by
  `deploy/nginx/conf.d/sicurre.com.conf`.
- Ensure the shared `nginx-proxy` container exists and the deploy user is in the
  Docker group.

## Better Auth and Turnstile

Production Better Auth persistence uses the dedicated Neon PostgreSQL `auth`
schema. SQLite is restricted to local development and smoke tests. Keep the
sidecar interface and never point a local process at the production auth schema.

`TURNSTILE_SITE_KEY` and `TURNSTILE_SECRET_KEY` are scoped to `deploy/env.auth`.
The signup form fetches the public site key from `/api/auth/config`, renders the
widget, and sends its short-lived token with `/sign-up/email`. Better Auth's
before hook validates it through Cloudflare Siteverify and fails closed when a
configured challenge is missing, expired, replayed, or invalid.

## Grafana

Alloy can start once `deploy/env.alloy` contains working Prometheus, Loki, and
OTLP ingestion credentials. Dashboard inspection/provisioning still needs:

```text
GRAFANA_URL=https://<stack>.grafana.net
GRAFANA_SERVICE_ACCOUNT_TOKEN=<dashboards:read, dashboards:write, folders:read, folders:write>
```

Sicurre and Sicurre-ML use separate telemetry identities and `stack` labels in
the shared Grafana tenant. Keep service dashboards and drill-down queries scoped
to those labels so one repository cannot obscure the other.

## Quarantine Custody And Release

The production quarantine custody contract is:

- create a private `sicurre-quarantine` R2 bucket;
- keep `SICURRE_QUARANTINE_RETENTION_DAYS=14` (the default);
- provision the managed R2 lifecycle rule during CD for the `quarantine/` prefix;
- run the daily database-aware purge from `sicurre-crontab.example`;
- configure the `SICURRE_QUARANTINE_*` values in `deploy/env.api`;
- grant the customer Cloudflare token `Email Sending: Edit`;
- enable an Email Sending domain for each connected zone; and
- run a controlled held-message release and confirm the original MIME reaches
  the configured destination exactly once.

The daily purge deletes the MIME before marking the database row deleted and
scrubs sender, subject, body, hash, size, and storage location. A failed object
deletion remains held and is retried on the next run. R2 lifecycle expiry is an
independent backstop and is verified during deployment.

If any custody upload fails, the Worker does not discard the message. If
inference is unavailable, it preserves mail availability but marks the
forwarded message as unscanned through `X-Sicurre-Scan-Status` instead of
asserting a safe verdict.

## Dependency Security Follow-up

Node production dependencies are audited in blocking CI with
`npm audit --omit=dev --audit-level=high`. The Better Auth and Express
advisories found during this deployment pass were upgraded and the audit is
clean.

The Python runtime dependency set is audited in blocking CI with `pip-audit`
over the exported `runtime` group (see `.github/workflows/ci.yml`). Advisories
that only affect notebook and data-exploration packages outside that group are
listed as explicit `--ignore-vuln` entries in the workflow so the exception is
visible and reviewable.
