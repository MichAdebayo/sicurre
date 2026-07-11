# ADR-0006: Cloudflare token scope selection

Status: Accepted

Supersedes: `0006-scope-selection-gmail_superseded.md`

## Context

Sicurre provisions Cloudflare Email Routing, Email Worker, and DNS records for protected domains. The user supplies a Cloudflare API token during setup.

## Decision

Use least-privilege, zone-scoped Cloudflare API tokens. The token must allow the selected zone to:

- read zone metadata
- read and edit DNS records
- enable/read Email Routing
- create/read/update Email Routing rules
- create/read/update Worker scripts needed for the Sicurre Email Worker

The app verifies the token before setup through `POST /v1/integrations/cloudflare/verify-token`.

## Consequences

- Sicurre setup no longer requests Gmail OAuth scopes.
- Token setup instructions must point users to Cloudflare dashboard permissions, not Google Cloud verification.
- Tokens must never be logged. Production storage should encrypt the token at rest.
- The UI should clearly explain that mailbox destination verification still happens through Cloudflare email confirmation.
