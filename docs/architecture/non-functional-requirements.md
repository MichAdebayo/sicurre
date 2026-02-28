# Non-functional requirements (NFRs)

## Performance
- p95 classify latency < 200ms (model endpoint)
- p95 end-to-end remediation < 5s (delivery → Trash)

## Reliability
- At-least-once Pub/Sub delivery → idempotent processing required
- Retry with exponential backoff on Gmail API transient failures
- Dead-letter queue for repeated failures (later)

## Security
- Least privilege OAuth scopes
- Encrypt tokens and any stored content at rest
- No secrets in repo; use Secret Manager

## Privacy
- Data minimization: store only what is required
- Provide user export + deletion

## Operability
- Structured logs (JSON)
- Metrics: request count, latency, verdict counts, remediation counts
- Alerts: listener failures, watch expiry, error rate spikes
