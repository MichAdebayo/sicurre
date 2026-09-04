# Changelog

Versions follow [semantic versioning](https://semver.org). Tags and per-release
notes are generated from Conventional Commits by semantic-release and published
to [GitHub Releases](https://github.com/MichAdebayo/sicurre/releases), which is
the authoritative record. This file summarises the notable changes only.

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
