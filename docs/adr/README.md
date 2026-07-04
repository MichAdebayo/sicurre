# ADRs (Architecture Decision Records)

ADRs capture decisions that matter, including context, alternatives, and consequences.

## Rules
- Don’t rewrite accepted ADRs; create a new ADR that supersedes a prior one.
- Use `Status: Proposed | Accepted | Superseded | Deprecated`.
- Keep them short and explicit.
## Index

| ADR | Title | Status | Visibility |
|-----|-------|--------|------------|
| [0001](0001-cloudflare-email-routing-runtime.md) | Cloudflare Email Routing runtime | Accepted | Public |
| [0001-superseded](0001-post-delivery-gmail_superseded.md) | Post-delivery Gmail integration via Pub/Sub | Superseded | Private |
| [0002](0002-camembertv2-french-base-model.md) | CamemBERTav2 (DeBERTaV3) 3-class ONNX inference | Accepted | Public |
| [0003](0003-fastapi-hetzner-sidecar-runtime.md) | FastAPI on Hetzner with Better Auth sidecar | Accepted | Public |
| [0003-superseded](0003-fastapi-cloud-run_superseded.md) | FastAPI + Cloud Run for API and services | Superseded | Public |
| [0004](0004-postgres-neon.md) | Neon PostgreSQL (prod) + SQLite (dev) | Accepted | Public |
| [0005](0005-open-core-oss-model-paid-saas.md) | Open-core OSS model distribution | Accepted | Public |
| [0006](0006-cloudflare-token-scope-selection.md) | Cloudflare token scope selection | Accepted | Public |
| [0006-superseded](0006-scope-selection-gmail_superseded.md) | Gmail OAuth scope selection | Superseded | Private |
| [0007](0007-cloudflare-worker-idempotency.md) | Cloudflare Worker scan idempotency | Accepted | Public |
| [0007-superseded](0007-idempotency-pubsub-history_superseded.md) | Idempotency strategy for Pub/Sub history | Superseded | Private |
| [0008](0008-better-auth.md) | Better Auth as authentication layer | Accepted | Public |
| [0009](0009-caching-and-rate-limiting.md) | Caching strategy and rate limiting | Accepted | Public |
