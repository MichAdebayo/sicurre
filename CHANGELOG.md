# Changelog

Versions follow [semantic versioning](https://semver.org). Tags and per-release
notes are generated from Conventional Commits by semantic-release and published
to [GitHub Releases](https://github.com/MichAdebayo/sicurre/releases), which is
the authoritative record. This file summarises the notable changes only.

## [Unreleased] - 2026-09-12

Deployed from `main` without a version tag: refactor commits do not bump the
version.

- The Cloudflare router is split by concern. `routers/integrations.py` keeps
  connect, status and disconnect; `routers/email_scan.py` holds the two routes
  the Email Worker calls; `routers/cloudflare_account.py` holds the domain
  preview, the token check and the stored token; the SPF, DKIM and DMARC record
  logic is a pure module, `services/dns_records.py`. Routes, schemas and the
  OpenAPI contract are unchanged. Unused SQLite helpers and an unused response
  schema were removed.
- The moved code is covered before it moves: new tests for the scan's
  idempotent replies, rule matching, notification opt-out and failure paths,
  the MIME custody refusals, the token check refusals, the record helpers and
  the auto-configuration write path.

## [1.33.1] - 2026-09-12

- The always-dark public pages (landing, login, contact, legal) use fixed
  `night-*` tokens from the brand's dark palette instead of slate classes and
  hex values; one of those literals had left the contact button at 1.8:1.

## [1.33.0] - 2026-09-12

- Connecting a domain starts with the domain name alone. A token-free preview
  reads public DNS and says whether the zone is on Cloudflare, who receives its
  mail today, and what connecting would add or modify; unsupported setups stop
  there. The token step follows, with a pre-filled Cloudflare link and the
  consent plan before anything is written.
- The Domain Shield auto-configuration card is a task list again: green when
  nothing needs work, SPF and DMARC rows with their checkboxes when something
  does. A per-domain panel in Settings shows what Sicurre writes on a zone and
  what it only reads.

## [1.32.2] - 2026-09-11

- Dialogs are real modals: labelled, focus kept inside, Escape closes, focus
  returns. Form errors are announced, every control shows a keyboard focus
  ring, notifications are keyboard-operable, and the eight public pages pass
  axe with no violation.

## [1.32.0] and [1.32.1] - 2026-09-11

- Verifying a token reads the zone and shows what connecting would change,
  record by record, with the option to decline a write; provisioning only
  starts on a second, explicit click.

## [1.31.0] - 2026-09-11

- The Cloudflare token can be created from a link with the five permissions
  already ticked, instead of a list to reproduce by hand.

## [1.29.0] to [1.30.0] - 2026-09-11

- The database keepalive is a switch (`SICURRE_DB_KEEPALIVE_ENABLED`), a
  readiness endpoint reports a database the API cannot reach, and the Grafana
  runtime dashboard shows database reachability with an alert on it.

## [1.28.3] - 2026-09-08

- Signing out, or a session expiring, clears every cached query and every
  tenant-scoped key in browser storage, so the next account on the same
  browser never sees the previous one's data.

## [1.28.1] and [1.28.2] - 2026-09-07

- Domain Shield: SPF is matched by content rather than position, the published
  include is the one Email Routing needs and the two wrong ones are withdrawn,
  DKIM is observed and never written, the certificate lifetime is measured
  rather than assumed, and one shield status is kept per workspace.
- Connecting refuses a domain whose inbound mail is served by another provider,
  since Email Routing would take that mail over.
- Disconnecting withdraws Sicurre's DMARC reporting address from the zone, and
  the zone read follows pagination so a large zone cannot produce a duplicate
  SPF record.

## [1.27.3] to [1.28.0] - 2026-09-05

- DMARC aggregate reports sent to a subdomain match their onboarded zone and
  are no longer quarantined as phishing; mail to a reporting address stays on
  the scan path; a single Worker source is deployed and re-provisioning no
  longer disarms ingestion.
- Alerts name the recipient's domain and are filed in a live workspace; the
  DMARC numbers on Domain Shield say what they mean for the reader.
- A credential that reached the logs in plaintext is now redacted at the
  source.

## [1.27.2] - 2026-09-04

- Decode RFC 2047 headers and extract the MIME body at scan entry, so the rules,
  the classifier, the audit row and the alert all see the message a human reads.
- Render the French explanation that accompanies each verdict in the threat
  journal. It was stored and served, but never displayed.
- Dataset release runs on the 13th of each month.
- A sustained npm advisories outage warns instead of blocking; a real high or
  critical finding still fails the build.

## [1.27.1] - 2026-09-04

- Send the `sender` variable the Loops template declares. Quarantine alerts were
  failing with a 400 and never reaching the customer.

## [1.27.0] - 2026-09-04

- Record the model version and revision that produced each verdict, so a
  decision can be attributed to the model that made it.

## [1.26.0] - 2026-09-02

- Raise legitimate-message generation to 10k and collapse tracking links.
- Mirror the phishing-recall margin in the promotion gate cross-check.

Earlier releases predate this file; see
[GitHub Releases](https://github.com/MichAdebayo/sicurre/releases). The move to
Cloudflare Email Routing as the runtime, which returns verdicts on the delivery
path rather than after delivery, is recorded in
[ADR-0001](docs/adr/0001-cloudflare-email-routing-runtime.md).
