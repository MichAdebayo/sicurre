# ADR-0001: Post-delivery Gmail remediation architecture

**Date:** 2026-02-28  
**Status:** Superseded by [ADR-0001: Cloudflare Email Routing runtime](0001-cloudflare-email-routing-runtime.md)  
**Deciders:** Adebayo Michael  

## Context
Sicurre targets auto-entrepreneurs and TPEs, many using personal gmail.com accounts. Pre-delivery interception (MX control) is not feasible for these users.

## Decision
Use a post-delivery workflow:
- Configure Gmail push notifications using `users.watch` to a Pub/Sub topic
- Process Pub/Sub push events on Cloud Run
- Fetch message changes, classify, and move phishing emails to Trash

## Alternatives considered
- MX/SMTP relay pre-delivery: requires custom domain + DNS changes
- Google Workspace routing rules: requires Workspace admin and paid plan
- Polling Gmail: higher latency and cost

## Consequences
**Positive:** Works for gmail.com; fast enough; minimal ops.  
**Negative:** Email can appear briefly before being moved.  
**Risk:** Pub/Sub at-least-once delivery requires idempotency.
