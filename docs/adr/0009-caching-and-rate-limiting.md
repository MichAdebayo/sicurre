# ADR-0009: Caching strategy and rate limiting

**Date:** 2026-02-28  
**Status:** Accepted  

## Context

Sicurre's hot path — Cloudflare Email Worker delivery → Sicurre API scan → classifier inference → DB/quarantine write — must complete within the runtime SLO in goals-scope-metrics.md. Three components create avoidable latency on every request:

1. **DMARC/SPF DNS lookups** — each call to `dmarc`/`checkdmarc` resolves sender domain DNS records (~30–80ms round-trip). The same domains recur across users (e.g., `urssaf.fr`, `impots.gouv.fr`, all major phishing impersonation targets).
2. **Cloudflare integration lookup** — scan and provisioning routes need workspace/domain integration state, but the same domain is read repeatedly during bursts.
3. **Classifier re-inference on duplicate content** — phishing campaigns deliver the same email to hundreds of users simultaneously. Re-running CamemBERTav2 ONNX inference (~80–150ms) on identical content is wasteful.
4. **Session validation** — Better Auth session lookup hits the DB (`sessions` table) on every authenticated API call.

Additionally, the public API exposes expensive inference and provisioning endpoints that must be protected from abuse and cost overruns. Host process scaling does not cap per-user spend by itself.

No caching or rate limiting was documented anywhere in the existing architecture docs.

---

## Decision

### Caching

Use a **two-tier strategy**: in-process cache for MVP (single host/runtime process), with a defined upgrade path to Redis when horizontal scaling requires shared state.

#### Tier 1 — In-process cache (MVP)

Implemented with Python's `cachetools` library (TTL-aware LRU caches, thread-safe with `TTLCache`).

| Cache | Key | TTL | Max entries | Implementation |
|-------|-----|-----|-------------|----------------|
| **DMARC/SPF lookup** | `sha256(sender_domain)` | 30 min | 1 000 | `TTLCache` in `dmarc_checker.py` |
| **Cloudflare integration status** | `workspace_id:domain` | 5 min | 10 000 | `TTLCache` in integration service |
| **Classifier result** | `sha256(subject + body + sender)` | 6 hours | 5 000 | `TTLCache` in `classifier.py` |
| **Session validation** | `session_token` | 5 min | 20 000 | `TTLCache` in auth middleware |

**Eviction:** All caches use TTL-based eviction + LRU size cap. Integration writes invalidate or bypass the short status cache; stale classifier results are acceptable within a 6-hour window.

**Caveat:** In-process caches are **per-process**. With multiple concurrent instances, each instance warms its own cache independently. This is acceptable for MVP because:
- DMARC lookups being duplicated across 2–3 instances adds at most ~160ms extra DNS traffic — negligible.
- Cloudflare integration status reads are cheap and short-lived.
- Classifier cache hit rate per-instance is still significant during active phishing campaigns (same email → same instance via request routing).

#### Tier 2 — Redis / Upstash (scale trigger)

Migrate to **Upstash Redis** (serverless, HTTP-based, no persistent connection required) when **any** of the following thresholds are crossed:

| Trigger | Threshold |
|---------|-----------|
| Active instances | > 3 simultaneous runtime instances |
| Classifier cache miss rate | > 40% on duplicate hashes (monitor via Prometheus counter) |
| Integration lookup latency | p95 > 150ms |
| Rate limiter correctness | Per-user limits are being bypassed due to per-instance state |

When migrating: swap `TTLCache` for Upstash Redis calls via `upstash-redis` Python client. The cache abstraction layer (`cache_backend.py`) ensures this is a single-file change, not a refactor.

---

### Rate limiting

Implemented with **`slowapi`** (FastAPI-native `limits` wrapper, analogous to Flask-Limiter).

Storage backend: **in-process** for MVP → **Redis** at scale (shared state requirement for correctness).

#### Limits per endpoint

| Endpoint | Limit | Scope | Rationale |
|----------|-------|-------|-----------|
| `POST /v1/model/classify` | 60 req/min (free), 600 req/min (pro), 3 000 req/min (business) | Per API key | Inference is the most expensive operation (~100ms GPU/CPU) |
| `POST /v1/email/scan` | High bounded internal limit | Worker secret + workspace/domain | Cloudflare Worker hot path; must reject forged traffic quickly |
| `GET /v1/threats` | 120 req/min | Per user (session) | Read-heavy, acceptable burst |
| `POST /v1/threats/{id}/status` | 30 req/min | Per user | Prevents rapid status churn |
| `POST /v1/feedback` | 60 req/min | Per user | Prevents feedback flooding (training data poisoning) |
| `GET /v1/quarantine` | 120 req/min | Per user | Read-heavy, acceptable burst |
| `POST /v1/quarantine/{id}/release` | 30 req/min | Per user | User-visible delivery action |
| `POST /v1/integrations/cloudflare/setup` | 10 req/hour | Per workspace | Provisioning action with external API side effects |
| Better Auth `/api/auth/*` | Provider defaults + reverse proxy limits | Per IP/session | Anti-automation for auth initiation |

#### Response on limit exceeded
- HTTP `429 Too Many Requests`
- Header: `Retry-After: <seconds>`
- Body: `{"error": "rate_limit_exceeded", "retry_after": <seconds>}`
- **Do not** return the user's current quota in the response (information disclosure risk).

#### Plan-based limits
User plan is read from the authenticated session or workspace membership lookup cached for 5 min. The `POST /v1/model/classify` endpoint uses a plan-aware key: `f"{api_key}:{plan}"` so limit tiers are enforced per key per plan.

---

## Alternatives considered

| Option | Reason rejected |
|--------|----------------|
| **Redis from day 1** | Adds €15–25/month (Upstash paid tier required for > 10K commands/day) and ops complexity before proving scale need. In-process cache is sufficient for < 500 MAU. |
| **Django cache framework** | Not using Django (ADR-0003). |
| **Google Cloud Memorystore** | €40+/month minimum and no longer aligned with the current non-GCP runtime. |
| **No caching at all** | DMARC DNS lookups + repeated integration reads add avoidable latency per email processed. |
| **No rate limiting** | A single user repeatedly calling inference/provisioning endpoints could exhaust runtime budget and inference capacity for all other users within minutes. |

---

## Consequences

- **Added dependency:** `cachetools` + `slowapi` + `limits` (all pure Python, lightweight).
- **MVP simplicity:** No external services required; zero infrastructure cost added.
- **Hot path latency improvement:** reduced repeated DNS/integration lookup cost on cache hit.
- **Correctness note:** In-process rate limiting is per-instance (not globally exact). A user could exceed their limit by a factor of N (number of instances) during a burst if routed to multiple instances. This is acceptable for MVP; migrate to Redis-backed `slowapi` when correctness matters.
- **Security:** Rate limiting on `/v1/model/classify`, `/v1/email/scan`, and provisioning routes directly supports DoS mitigation.
- **Cache poisoning risk:** Classifier cache key is `sha256(subject + body + sender)` — content-addressed, so collision attacks are negligible. Integration status cache is short-lived and invalidated by provisioning writes.
