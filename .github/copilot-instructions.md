# Copilot Instructions — Sicurre

Sicurre is a **French-native, real-time phishing detection and inbox remediation system** for Gmail (later M365). It targets French auto-entrepreneurs and TPEs. A fine-tuned CamemBERTv2 model classifies emails; confirmed phishing is automatically moved to Trash via the Gmail API within 2 seconds of delivery.

Read `docs/architecture/component-design.md` and `docs/architecture/data-design.md` before making changes to the API or database layer.

---

## Tech Stack

| Layer | Choice | Decision |
|-------|--------|----------|
| Language | Python 3.11+ | — |
| API framework | FastAPI + Pydantic v2 | ADR-0003 |
| Inference runtime | ONNX Runtime (INT8 quantized CamemBERTv2) | ADR-0002 |
| Database (prod) | Neon PostgreSQL via SQLAlchemy / SQLModel | ADR-0004 |
| Database (dev/CI) | SQLite (same ORM models, dialect abstraction) | ADR-0004 |
| Auth | Better Auth (Node.js sidecar or REST proxy) | ADR-0008 |
| Email integration | Gmail API + Google Pub/Sub push | ADR-0001 |
| Caching | `cachetools.TTLCache` (in-process MVP), Upstash Redis at scale | ADR-0009 |
| Rate limiting | `slowapi` (FastAPI-native) | ADR-0009 |
| Deployment | Google Cloud Run (all services) | ADR-0003 |
| Package manager | `uv` (`pyproject.toml` with `[tool.uv] package = false`) | — |
| CI/CD | GitHub Actions | — |
| Monitoring | Prometheus + Grafana | — |

---

## Architecture Rules

These rules are non-negotiable. Do not generate code that violates them.

### DB access
- **Only `Sicurre API` (FastAPI) holds a Postgres/SQLite connection.** Gmail Listener and Phishing API never query the DB directly — they call the Sicurre API over HTTP.
- All DB queries filtering user data **must** include `WHERE user_id = <session_user_id>`. Never trust `user_id` from the request body.
- Use SQLAlchemy / SQLModel with dialect abstraction so the same models work against both SQLite (dev) and Neon PostgreSQL (prod).

### Component boundaries
- `gmail-listener` (Cloud Run): receives Pub/Sub push → fetches message → calls `phishing-api` → calls Sicurre API to write audit log. No direct DB.
- `phishing-api` (Cloud Run): classification + DMARC/URL signals only. Stateless. No DB.
- `sicurre-api` (Cloud Run): auth, user settings, audit log, public API surface. Owns DB.
- Dashboard (Streamlit POC / React prod): calls Sicurre API only. No direct DB, no direct Gmail calls.

### Idempotency
- All Pub/Sub push handlers must be idempotent. Use `UNIQUE (user_id, message_id)` on `threat_log` as the deduplication guard, not application-level locks (see ADR-0007).

---

## Security Rules

### IDOR prevention
Every endpoint that returns or modifies user-scoped data must scope queries to the authenticated session user:
```python
# Correct
threat = db.get(ThreatLog, id, user_id=current_user.id)

# Wrong — never do this
threat = db.get(ThreatLog, request.body.id)
```

### OAuth tokens
- Never log, return in API responses, or store unencrypted refresh tokens.
- Refresh tokens are stored AES-256-GCM encrypted in `oauth_tokens.encrypted_refresh_token`.
- Access tokens are cached in-process for 55 minutes (`TTLCache` keyed by `user_id`) — never written to DB.

### Secrets
- Never hardcode credentials, connection strings, or keys.
- Dev: `.env` file (gitignored). Prod: GCP Secret Manager.
- Do not commit anything to `docs/ops/`, `docs/architecture/threat-model.md`, `docs/architecture/privacy-rgpd.md`, or `docs/adr/0001-*`, `docs/adr/0006-*`, `docs/adr/0007-*` — these are gitignored private files.

### Rate limiting
Every new public endpoint must have a `slowapi` rate limit decorator. Reference the rate limit table in `docs/adr/0009-caching-and-rate-limiting.md` for precedents. Destructive endpoints (trash, delete) get the strictest limits.

---

## Privacy Rules (RGPD)

- **Do not store raw email bodies by default.** If a feature requires storing email content, it must be opt-in, anonymized, and TTL-bounded (7–90 days max).
- Anonymize PII in any stored text: replace with `[EMAIL]`, `[PHONE]`, `[IBAN]`, `[URL]`.
- API error responses must never include stack traces, internal state, or DB details.
- Structured logs must run through a PII redaction filter before emission.

---

## Python Conventions

- Python 3.11+. Use `match` statements over `if/elif` chains for verdict/action enums.
- Type-annotate all function signatures. Use Pydantic v2 models for all request/response schemas.
- `async def` for all FastAPI route handlers and any I/O-bound work (DB, Gmail API, HTTP calls).
- Use `httpx.AsyncClient` (not `requests`) for outbound HTTP calls in async context.
- Environment config via `pydantic-settings` `BaseSettings` — never `os.environ` scattered in business logic.
- SQL migrations via Alembic. Never run raw DDL in application startup.

---

## Caching Conventions

Follow the two-tier strategy in ADR-0009:
```python
from cachetools import TTLCache
from cachetools.keys import hashkey

# DMARC: 30 min, 1 000 entries
_dmarc_cache: TTLCache = TTLCache(maxsize=1_000, ttl=1_800)

# Access token: 55 min, 10 000 entries  
_token_cache: TTLCache = TTLCache(maxsize=10_000, ttl=3_300)

# Classifier result: 6 hours, 5 000 entries
_classifier_cache: TTLCache = TTLCache(maxsize=5_000, ttl=21_600)
```
Cache keys for classifier results are `sha256(subject + body + sender)` — never cache by `message_id` alone (different users, same content must hit the cache).

---

## Testing

- Use `pytest` with `pytest-asyncio` for async route tests.
- Every endpoint that reads user data needs an **IDOR test**: authenticated as User A, attempt to access User B's resource, assert `403` or `404`.
- Test idempotency on the Pub/Sub handler: send the same `message_id` twice, assert only one `threat_log` row is created.
- Use SQLite in-memory (`sqlite:///:memory:`) for all DB tests — no Neon connection required in CI.
- Mock Gmail API calls with `respx` or `pytest-httpx`.

---

## API Contract

The authoritative API spec is `docs/api/openapi.yaml`. When adding endpoints:
1. Add the path + schemas to `openapi.yaml` first.
2. Implement the FastAPI route to match exactly.
3. Add a JSON example to `docs/api/examples/` if the endpoint has a non-trivial request/response.

---

## Key Docs

| What | Where |
|------|-------|
| Product goals + success metrics | `docs/architecture/goals-scope-metrics.md` |
| C4 L1 system context | `docs/architecture/system-context.md` |
| C4 L2 component design | `docs/architecture/component-design.md` |
| Full DB schema (MCD + ER) | `docs/architecture/data-design.md` |
| NFRs (latency, security, privacy) | `docs/architecture/non-functional-requirements.md` |
| All architectural decisions | `docs/adr/` |
| OpenAPI spec | `docs/api/openapi.yaml` |
| Doc visibility policy | `docs/README.md` |
