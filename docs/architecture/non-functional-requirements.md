# Non-functional requirements (NFRs)

## Performance
- p95 classify latency < 200ms (model endpoint)
- p95 end-to-end remediation < 5s (delivery → Trash)
- DMARC/SPF DNS results cached 30 min (in-process `TTLCache`)
- Gmail access tokens cached 55 min per user (below Google's 60 min expiry)
- Classifier results cached 6 hours by content hash (deduplicates phishing campaigns)
- Session validation cached 5 min in-process
- See ADR-0009 for full caching strategy and Redis upgrade triggers

## Reliability
- At-least-once Pub/Sub delivery → idempotent processing required
- Retry with exponential backoff on Gmail API transient failures
- Dead-letter queue for repeated failures (later)

## Security
- Least privilege OAuth scopes
- Encrypt tokens and any stored content at rest
- No secrets  committed to repo
- All local dev secrets should be in .env
- use Secret Managers for prod secrets
- Rate limits enforced per user/API key on all public endpoints (slowapi); see ADR-0009 for per-endpoint limits

## Privacy
- Data minimization: store only what is required
- Provide user export + deletion

## Operability
- Structured logs (JSON)
- Metrics: request count, latency, verdict counts, remediation counts
- Alerts: listener failures, watch expiry, error rate spikes
