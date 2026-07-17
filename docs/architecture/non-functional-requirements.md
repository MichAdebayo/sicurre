# Non-functional requirements (NFRs)

## Performance
- Target: p95 classify latency < 1s without LLM and < 8s with LLM; attach measured Sicurre-ML load evidence before treating either as an SLO.
- Target: p95 end-to-end classification/quarantine < 5s (Cloudflare Email Worker delivery → Sicurre verdict); production email evidence remains required.
- DMARC/SPF DNS results cached 30 min (in-process `TTLCache`)
- Cloudflare integration status cached briefly for UI reads only
- Classifier result caching is not part of the current application runtime.
- Better Auth sessions are revalidated on every protected API request so revocation takes effect immediately.
- See ADR-0009 for full caching strategy and Redis upgrade triggers

## Reliability
- Cloudflare Worker/API retry semantics require idempotent processing
- Retry with exponential backoff on Cloudflare API transient failures
- Dead-letter queue for repeated failures (later)

## Security
- Least-privilege Cloudflare API-token permissions and service-to-service Bearer credentials
- Encrypt tokens and any stored content at rest
- No secrets  committed to repo
- All local dev secrets should be in .env
- Production secrets are server-owned environment files with restricted filesystem permissions; migration to a dedicated secret manager remains an optional hardening step.
- Rate limits enforced per user/API key on all public endpoints (slowapi); see ADR-0009 for per-endpoint limits

## Privacy
- Data minimization: store only what is required
- Provide user export + deletion

## Operability
- Structured logs (JSON)
- Metrics: request count, latency, verdict counts, quarantine counts, feedback counts
- Alerts: Worker/API failures, inactive domains, error rate spikes
