# Grafana Observability

Grafana is for runtime operations: uptime, request rate, proxy failures, service
logs, and deploy health. Sicurre admin analytics should stay inside the app:
tenants, onboarding state, threat volume, quarantine actions, feedback, DMARC
reports, and product usage.

## Current Code-Provisioned Assets

- `dashboards/*.json`: the versioned Grafana dashboards for the production app
  stack (runtime overview, infrastructure, telemetry pipeline, alert-chain
  evidence), provisioned by CD on every deployment.
- `../../scripts/deploy/provision_grafana_dashboard.mjs`: idempotent dashboard
  and alerting importer.
- `alerts/sicurre-alerts.json`: versioned availability, error-rate, latency,
  telemetry-collector, and controlled-exercise alert rules routed to the Sicurre
  operations contact point.
- `../alloy/config.alloy`: ships Docker logs and app gateway metrics.

## Access Needed To Inspect Or Provision Grafana

The existing `.env` contains Grafana/Loki/Prometheus ingestion credentials, but
dashboard inspection/provisioning usually needs one extra value:

```text
GRAFANA_URL=https://<your-stack>.grafana.net
GRAFANA_SERVICE_ACCOUNT_TOKEN=<token with dashboard, folder, datasource, alert-rule, and notification provisioning rights>
```

The ingestion token in `GRAFANA_API_TOKEN` may or may not have dashboard API
permissions. If it is only a Metrics/Loki publisher token, create a separate
Grafana service account token for dashboard management.

Provision the dashboards, contact point, notification policy, and rules with:

```bash
GRAFANA_URL="https://<your-stack>.grafana.net" \
GRAFANA_SERVICE_ACCOUNT_TOKEN="<dashboard-token>" \
make grafana-provision
```

## Suggested Dashboard Separation

- `Vinse / Runtime`: keep Vinse-only service health and logs.
- `Sicurre / App Runtime`: app gateway, FastAPI, Better Auth, Cloudflare
  integration errors, deployment health.
- `Sicurre / ML Runtime`: inference latency, ready state, model load, classifier
  errors, Redis/cache health.
- `Sicurre / Product Admin`: build this in the Sicurre app, not Grafana.
