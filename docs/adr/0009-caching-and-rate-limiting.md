# ADR-0009: Caching strategy and rate limiting

**Date:** 2026-02-28  
**Status:** Accepted  

## Context

Sicurre's hot path — Pub/Sub push → Gmail API fetch → classifier inference → DB write — must complete in under 2 seconds (p95 TTR goal from goals-scope-metrics.md). Three components create avoidable latency on every request:

1. **DMARC/SPF DNS lookups** — each call to `dmarc`/`checkdmarc` resolves sender domain DNS records (~30–80ms round-trip). The same domains recur across users (e.g., `urssaf.fr`, `impots.gouv.fr`, all major phishing impersonation targets).
2. **Gmail access token exchange** — after reading the encrypted refresh token from DB, we exchange it for a short-lived access token via Google's token endpoint (~100–200ms). Access tokens are valid for 1 hour and can be reused across requests.
3. **Classifier re-inference on duplicate content** — phishing campaigns deliver the same email to hundreds of users simultaneously. Re-running CamemBERTv2 ONNX inference (~80–150ms) on identical content is wasteful.
4. **Session validation** — Better Auth session lookup hits the DB (`sessions` table) on every authenticated API call.

Additionally, the public API exposes an expensive inference endpoint (`/v1/classify`) that must be protected from abuse and cost overruns. Cloud Run's auto-scaling handles burst concurrency but does not cap per-user spend.

No caching or rate limiting was documented anywhere in the existing architecture docs.

---

## Decision

### Caching

Use a **two-tier strategy**: in-process cache for MVP (single Cloud Run instance), with a defined upgrade path to Redis when horizontal scaling requires shared state.

#### Tier 1 — In-process cache (MVP)

Implemented with Python's `cachetools` library (TTL-aware LRU caches, thread-safe with `TTLCache`).

| Cache | Key | TTL | Max entries | Implementation |
|-------|-----|-----|-------------|----------------|
| **DMARC/SPF lookup** | `sha256(sender_domain)` | 30 min | 1 000 | `TTLCache` in `dmarc_checker.py` |
| **Gmail access token** | `user_id` | 55 min | 10 000 | `TTLCache` in `token_manager.py` (55 min < Google's 60 min ticket) |
| **Classifier result** | `sha256(subject + body + sender)` | 6 hours | 5 000 | `TTLCache` in `classifier.py` |
| **Session validation** | `session_token` | 5 min | 20 000 | `TTLCache` in auth middleware |

**Eviction:** All caches use TTL-based eviction + LRU size cap. No explicit invalidation needed — tokens expire naturally before TTL; stale classifier results are acceptable within a 6-hour window.

**Caveat:** In-process caches are **per-instance**. On Cloud Run with multiple concurrent instances, each instance warms its own cache independently. This is acceptable for MVP because:
- DMARC lookups being duplicated across 2–3 instances adds at most ~160ms extra DNS traffic — negligible.
- Token exchange duplicated across instances is acceptable at low user counts (< 1 000 active users).
- Classifier cache hit rate per-instance is still significant during active phishing campaigns (same email → same instance via request routing).

#### Tier 2 — Redis / Upstash (scale trigger)

Migrate to **Upstash Redis** (serverless, HTTP-based, no persistent connection required — ideal for Cloud Run) when **any** of the following thresholds are crossed:

| Trigger | Threshold |
|---------|-----------|
| Active instances | > 3 simultaneous Cloud Run instances |
| Classifier cache miss rate | > 40% on duplicate hashes (monitor via Prometheus counter) |
| Token exchange latency | p95 > 150ms (rate limiter state must be shared for correctness) |
| Rate limiter correctness | Per-user limits are being bypassed due to per-instance state |

When migrating: swap `TTLCache` for Upstash Redis calls via `upstash-redis` Python client. The cache abstraction layer (`cache_backend.py`) ensures this is a single-file change, not a refactor.

---

### Rate limiting

Implemented with **`slowapi`** (FastAPI-native `limits` wrapper, analogous to Flask-Limiter).

Storage backend: **in-process** for MVP → **Redis** at scale (shared state requirement for correctness).

#### Limits per endpoint

| Endpoint | Limit | Scope | Rationale |
|----------|-------|-------|-----------|
| `POST /v1/classify` | 60 req/min (free), 600 req/min (pro), 3 000 req/min (business) | Per API key | Inference is the most expensive operation (~100ms GPU/CPU) |
| `GET /v1/threat-log` | 120 req/min | Per user (JWT) | Read-heavy, acceptable burst |
| `POST /v1/threat-log/{id}/restore` | 30 req/min | Per user | Prevents rapid restore-trash cycles |
| `POST /v1/feedback` | 60 req/min | Per user | Prevents feedback flooding (training data poisoning) |
| `GET /v1/stats` | 30 req/min | Per user | Aggregation query, moderate DB cost |
| `GET /auth/login/google` | 10 req/min | Per IP | Anti-automation for OAuth initiation |
| `POST /auth/logout` | 20 req/min | Per user | Low concern, basic protection |
| `POST /v1/remediate/gmail/trash` | 10 req/min | Per user | Destructive action — strict limit |
| `POST /gmail-listener` (Pub/Sub endpoint) | No rate limit | — | Google-managed push; JWT validation is the guard |

#### Response on limit exceeded
- HTTP `429 Too Many Requests`
- Header: `Retry-After: <seconds>`
- Body: `{"error": "rate_limit_exceeded", "retry_after": <seconds>}`
- **Do not** return the user's current quota in the response (information disclosure risk).

#### Plan-based limits
User plan is read from the authenticated session (claim or DB lookup cached for 5 min). The `POST /v1/classify` endpoint uses a plan-aware key: `f"{api_key}:{plan}"` so limit tiers are enforced per key per plan.

---

## Alternatives considered

| Option | Reason rejected |
|--------|----------------|
| **Redis from day 1** | Adds €15–25/month (Upstash paid tier required for > 10K commands/day) and ops complexity before proving scale need. In-process cache is sufficient for < 500 MAU. |
| **Django cache framework** | Not using Django (ADR-0003). |
| **Google Cloud Memorystore** | €40+/month minimum — too expensive for solo dev MVP. |
| **No caching at all** | DMARC DNS lookups + token exchange add ~200–300ms per email processed. With p95 TTR target of 5s, this overhead is visible and unnecessarily burned every time. |
| **No rate limiting** | A single user repeatedly calling `/v1/classify` could exhaust Cloud Run CPU budget and inference capacity for all other users within minutes. |

---

## Consequences

- **Added dependency:** `cachetools` + `slowapi` + `limits` (all pure Python, lightweight).
- **MVP simplicity:** No external services required; zero infrastructure cost added.
- **Hot path latency improvement:** estimated ~180–280ms reduction per email on cache hit (DMARC + token exchange).
- **Correctness note:** In-process rate limiting is per-instance (not globally exact). A user could exceed their limit by a factor of N (number of instances) during a burst if routed to multiple instances. This is acceptable for MVP; migrate to Redis-backed `slowapi` when correctness matters.
- **Security:** Rate limiting on `/v1/classify` directly supports the DoS mitigation documented in the threat model (STRIDE §5).
- **Cache poisoning risk:** Classifier cache key is `sha256(subject + body + sender)` — content-addressed, so collision attacks are negligible. Access token cache is keyed by `user_id` and TTL-bounded below Google's expiry, so stale token serving is impossible.
