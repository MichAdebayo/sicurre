# ADR-0001: Cloudflare Email Routing runtime

Status: Accepted

Supersedes: `0001-post-delivery-gmail_superseded.md`

## Context

The implemented product runtime no longer uses Gmail watches or Pub/Sub as the primary ingestion path. Sicurre now protects customer-owned domains by receiving inbound mail through Cloudflare Email Routing and a Cloudflare Email Worker.

The current implementation is documented and exercised through:

- `src/data_platform/api/routers/integrations.py`
- `src/data_platform/services/cloudflare_provisioner.py`
- `docs/email-intercept.md`

## Decision

Use Cloudflare as the runtime email ingress layer:

1. Customer delegates the domain to Cloudflare nameservers.
2. Cloudflare Email Routing receives inbound mail for the protected domain.
3. A Cloudflare Email Worker extracts message metadata/body and calls Sicurre API `POST /v1/email/scan`.
4. Sicurre API classifies the message, records the event, and returns a verdict.
5. The Worker forwards clean mail and holds or rejects high-risk mail according to policy.

The Sicurre API is publicly reachable over HTTPS on the Hetzner-hosted application server. The callback URL is configured with `SICURRE_PUBLIC_API_URL` / `PUBLIC_API_URL`.

## Consequences

- Gmail API and Pub/Sub are not runtime dependencies for inbound scanning.
- Users need a Cloudflare-managed domain, not necessarily a Google Workspace mailbox.
- Sicurre can support any destination inbox that Cloudflare Email Routing can forward to.
- Mailbox verification and DNS propagation remain user-visible setup steps.
- The product feedback loop is handled by Sicurre API and database records, not by GCP resources.
