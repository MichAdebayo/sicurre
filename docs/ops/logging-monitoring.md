# Logging and monitoring

Written from the sources on 3 September 2026. The previous version of this
document listed six metrics — `sicurre_classify_requests_total`,
`sicurre_classify_latency_ms`, `sicurre_phishing_detected_total`,
`sicurre_quarantine_items_total`, `sicurre_feedback_submissions_total`,
`sicurre_cloudflare_delivery_errors_total` — **none of which exist**, and
described JSON logs with a hashed workspace identifier that are not emitted.
It described a system that was never built.

Everything below names a file. If a claim here cannot be traced to one, it is
wrong and should be removed rather than implemented to match.

## Metrics

### Scan decision path — `src/core/scan_metrics.py`

The application's own view of an email reaching a verdict.

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `sicurre_scan_duration_seconds` | histogram | `verdict` | End-to-end time to a verdict, measured by the scan handler |
| `sicurre_scan_stage_duration_seconds` | histogram | `stage` | The same request split by stage |
| `sicurre_scan_total` | counter | `verdict` | Scan decisions reaching a verdict |
| `sicurre_scan_sla_breach_total` | counter | `verdict` | Scans whose decision exceeded the configured SLA |

Duration buckets are `0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 5.0, 10.0, 30.0`
seconds. The 2.0 boundary is real, so a two-second objective is measurable here
directly rather than by interpolation.

> **The SLA counter does not measure the stated objective.**
> `sicurre_scan_sla_breach_total` compares against `settings.sla_latency_ms`,
> which defaults to **10000** and is not overridden in production. The stated
> delivery objective is two seconds. As configured, the counter records
> breaches above ten seconds and stays at zero for everything between two and
> ten — so it reads healthy across the entire range the objective cares about.
> Setting `SICURRE_SLA_LATENCY_MS=2000` makes the metric mean what its name
> says. Until then, do not cite it as evidence the objective is met.

### Application gateway — `scripts/app/container_server.mjs`

The Node process in front of the SPA and the API.

| Metric | Type |
|--------|------|
| `sicurre_app_gateway_requests_total` | counter |
| `sicurre_app_gateway_responses_total` | counter |
| `sicurre_app_gateway_request_duration_seconds` | histogram |
| `sicurre_app_gateway_proxy_errors_total` | counter |
| `sicurre_app_gateway_uptime_seconds` | gauge |

Requests are bucketed by route class — `health`, `metrics`, `auth`, `api`,
`assets` — rather than by raw path, which keeps cardinality bounded.

### Operational exercise

`sicurre_operational_exercise_active` marks a controlled exercise window, so a
deliberate fault injection is distinguishable from a real incident in the same
series.

### The ML inference service

Its metrics are a separate surface documented in the companion repository.
Nothing in this file describes them, and the two must not be conflated: this
service measures the whole scan decision, the ML service measures time inside
its own classify handler.

## Logging

**The API emits plain Python `logging` lines, not JSON, and no workspace hash.**
The previous version of this document claimed otherwise. Formatters are
configured per entry point with `logging.basicConfig`, so the format is the
standard library default.

`SemanticTraceLogger` produces structured trace records for pipeline stages —
those *are* JSON, with `parent_type`, `child_target`, `domain`, `stage`,
`status`, `message`, `timestamp` and a bounded `metrics` object. They cover the
data platform's ingestion and normalization work, not the request path.

Adding a JSON formatter to the API's logging configuration is a small change,
and would make the two consistent. Until it happens this document should keep
saying plain lines, because that is what is shipped.

## Shipping

Grafana Alloy tails container stdout and ships to Grafana Cloud. Configuration
is in `deploy/alloy/`.

> **Log delivery is currently dropping entries.** Loki returns HTTP 400
> — `entry for stream {container="sicurre-prod-node-exporter-1" …} has timestamp
> too old` — with `no retries left, dropping data`, observed across 55 errors on
> 3 September 2026. Alloy is replaying a write-ahead log whose entries predate
> Loki's retention window. Metrics are unaffected; remote-write reports
> `Done replaying WAL` against the Prometheus endpoint. The fix is to truncate
> the WAL on restart or set a retention shorter than Loki's reject window.

## Alerts

Deployed rules are in `deploy/grafana/alerts/sicurre-alerts.json`:

| Rule |
|------|
| Sicurre API unavailable |
| Sicurre elevated 5xx rate |
| Sicurre latency above SLO |
| Sicurre telemetry collector unavailable |
| Sicurre controlled operational exercise |
| Sicurre active-series budget above 70% |
| Sicurre active-series budget above 85% |

There is **no rule on scan failures**. Incident 06 lists "alerter sur les
échecs" under prevention; it is an intention, not a deployed rule, and should be
described that way until one exists.

## A pattern worth naming

Three defects found on 2–3 September share a shape: a control that appears
present in code or documentation and is inert in fact. An alert threshold above
the histogram's ceiling that could never fire. An SLA counter configured at five
times the stated objective. A documented metric set that was never implemented.

Each looked healthy precisely because it was disconnected. When citing
monitoring as evidence, cite the series that carry data, and say which controls
are declared but unverified.
