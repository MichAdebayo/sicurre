# ADR-0007: Idempotency for Pub/Sub + Gmail history processing

**Date:** 2026-02-28  
**Status:** Superseded by [ADR-0007: Cloudflare Worker scan idempotency](0007-cloudflare-worker-idempotency.md)  

## Context
Pub/Sub delivers messages at least once; duplicates are possible. Gmail watch notifications provide history IDs; processing must not double-trash or double-log.

## Decision
Implement idempotency:
- Store last processed `historyId` per user
- Use `message_id` + action type as idempotency key in DB
- Ensure remediation endpoint is safe to retry

## Consequences
- Slightly more DB writes
- Prevents duplicate actions and inconsistent logs
