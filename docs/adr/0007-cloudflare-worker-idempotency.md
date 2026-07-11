# ADR-0007: Cloudflare Worker scan idempotency

Status: Accepted

Supersedes: `0007-idempotency-pubsub-history_superseded.md`

## Context

The runtime email path is Cloudflare Email Routing plus a Cloudflare Email Worker calling `POST /v1/email/scan`. Retries can still happen when the Worker or Sicurre API times out, even without Pub/Sub.

## Decision

Treat the Cloudflare Worker scan path as at-least-once delivery. Sicurre API must make scan persistence and follow-up actions idempotent by using workspace-scoped event identifiers when available and by constraining state changes to the authenticated workspace.

Current implementation records scan decisions in `app_inference_event` and quarantined messages in `app_quarantine_item`. The next hardening step is to persist a stable inbound message fingerprint from the Worker so duplicate Worker retries cannot create duplicate quarantine entries.

## Consequences

- Pub/Sub message IDs and Gmail history IDs are no longer idempotency keys.
- Runtime logs should carry Cloudflare Worker request IDs, integration ID, workspace ID, and Sicurre event ID.
- The database boundary remains: Cloudflare Worker never connects to the database; it calls Sicurre API only.
