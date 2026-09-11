# Grafana Alloy

`config.alloy` tails Docker logs for containers in the `sicurre-prod` compose
project, drops noisy health probes, forwards logs to Loki, and scrapes the
Sicurre app gateway `/metrics` endpoint for Prometheus remote write. It also
exposes an internal-only OTLP receiver on `4317`/`4318` that receives the
API's OpenTelemetry traces.

The Alloy container/runtime is usually installed as host infrastructure. Mount:

```text
deploy/alloy/config.alloy -> /etc/alloy/config.alloy
/var/run/docker.sock -> /var/run/docker.sock
```

Required environment variables:

```text
GRAFANA_PROMETHEUS_REMOTE_WRITE_URL
GRAFANA_PROMETHEUS_METRICS_USERNAME
GRAFANA_PROMETHEUS_METRICS_API_TOKEN
GRAFANA_LOKI_URL
GRAFANA_LOKI_USER
GRAFANA_LOKI_API_TOKEN
GRAFANA_OPEN_TELEMETRY_OTLP_ENDPOINT
GRAFANA_OPEN_TELEMETRY_INSTANCE_ID
GRAFANA_OPEN_TELEMETRY_API_TOKEN
```

`GRAFANA_GCX_TOKEN`, `GRAFANA_ACCESS_POLICY_TOKEN`, and a GitHub integration
PAT are operator credentials, not collector credentials. Keep them out of the
Alloy container and use them only from a secured operator shell or a dedicated
dashboard-provisioning workflow.
The cAdvisor container is intentionally excluded from Loki. Its health and
container-resource output are monitored as Prometheus metrics, while its
rotated local Docker logs remain available for server-side diagnosis.
