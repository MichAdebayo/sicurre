
```md
# Component design (C4 L2)

## Components

### 1a) POC Dashboard (Streamlit)
- Role: demonstrate end-to-end classifier pipeline: email input → verdict + signals + audit log
- Calls Sicurre API (FastAPI) only — no direct DB access
- Scope: Simplon evaluation + early user feedback; disposable after POC

### 1b) Production Dashboard (React/TypeScript)
- Role: user onboarding, logs, settings, restore actions
- Calls Sicurre API via JWT session — no direct DB access
- Replaces Streamlit entirely once core pipeline is validated

### 2) Sicurre API (FastAPI on Cloud Run)
- Role: auth, user settings, audit log access, public API surface
- Integrates with Neon PostgreSQL (prod) / SQLite (dev)

### 3) Gmail Listener (Cloud Run service/function)
- Role: receive Pub/Sub push, resolve message changes, call classifier, trigger remediation
- Must be idempotent due to at-least-once delivery

### 4) Phishing API / Classifier (FastAPI on Cloud Run)
- Role: classification + signal extraction
- Loads fine-tuned French model + hybrid signals (DMARC/URL heuristics)

### 5) Postgres (Neon — prod) / SQLite (dev)
- Role: user records, encrypted tokens, audit log, model version tagging
- Neon serverless PostgreSQL for production (autoscaling, branching for staging)
- SQLite for local development and CI (zero-config, fast)

## Key interfaces
- Pub/Sub push → Gmail Listener: HTTP endpoint secured by verification token/JWT
- Gmail Listener → Gmail API: OAuth token per user (encrypted at rest)
- Gmail Listener → Classifier: internal authenticated HTTP (service-to-service)
- Gmail Listener → Sicurre API: writes audit log via internal API call (not direct DB)
- Dashboard (Streamlit or React) → Sicurre API: JWT user auth
- **Sicurre API is the only component that holds a Postgres connection**

## Deployment boundaries
- Keep Listener and Classifier separate: different scaling/memory patterns
- Avoid too many microservices early; split only when needed
- DB access rule: only Sicurre API writes to/reads from Postgres; all other components go through the API contract
- POC (Streamlit) and production (React) are UI-layer swaps only; the API and backend pipeline remain unchanged
