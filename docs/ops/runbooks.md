# Runbooks

## Runbook: Cloudflare Email Routing stopped delivering

Symptoms:
- Threat log stops updating for one domain.
- Cloudflare dashboard shows Email Routing or Worker delivery errors.
- `cloudflare_integration.status` is `degraded` or `disconnected`.

Checks:
- Verify MX records for the protected domain point to Cloudflare Email Routing.
- Confirm the Cloudflare Email Worker is deployed and has the current scan URL.
- Confirm the Worker includes `X-Sicurre-Secret` and the API accepts it.
- Inspect `app_inference_event` for recent rows for the affected workspace/domain.

Fix:
- Re-run the Cloudflare integration setup from Domain Shield.
- Rotate and redeploy the Worker shared secret if authentication fails.
- Re-check DNS propagation before marking the incident resolved.

## Runbook: Duplicate Cloudflare Worker deliveries
Symptoms:
- Same message id logged twice

Fix:
- Ensure workspace-scoped event fingerprints are enforced.
- Treat repeated Worker calls as at-least-once delivery and make scan writes idempotent.

## Runbook: DMARC aggregate reports are not arriving

Domain Shield adds `rua=mailto:dmarc@sicurre.com` to a client's DMARC record,
asking receivers to send us their aggregate reports. Because that mailbox sits
on a different domain from the record, RFC 7489 7.1 makes the receiving domain
publish its consent, or a receiver that checks - Google and Microsoft both do -
silently declines to send. Nothing in the report or the dashboard says a report
was withheld; it simply never arrives.

**This is already handled, once, for every client present and future**, by a
wildcard on the sicurre.com zone:

```
*._report._dmarc.sicurre.com   TXT   "v=DMARC1;"
```

Onboarding a client therefore needs no DNS work on our side at all. This is the
same mechanism Cloudflare uses for its own DMARC reporting product - a random
label under `_report._dmarc.dmarc-reports.cloudflare.net` answers `v=DMARC1;`,
which is only possible with a wildcard.

Verify the consent chain for a client that is not receiving reports. All three
must answer:

```bash
dig +short TXT _dmarc.<client-domain>                          # names dmarc@sicurre.com
dig +short TXT <client-domain>._report._dmarc.sicurre.com      # our consent
dig +short MX  sicurre.com                                     # routes to the worker
```

If the middle one is empty the wildcard has been deleted or the zone is not
resolving; restore it before looking anywhere else. Aggregate reports are
generated about once a day per domain, so allow 24-48h before concluding a
change did or did not work.

**Why not a record per client.** Per-domain records are more precise and give an
audit trail, but each one publicly names a client of Sicurre in DNS, and each is
a manual step that has to happen before reports flow. The wildcard names nobody
and cannot be forgotten. Its cost is that any domain on the internet may direct
reports at `dmarc@sicurre.com`; the ingest endpoint requires the Worker's shared
secret, caps message size, and returns `ignored` for a domain with no active
integration, so an unrecognised report is discarded rather than stored.

**On teardown.** Disconnecting a client withdraws `dmarc@sicurre.com` from their
DMARC record automatically, so they stop reporting to us. Nothing needs removing
on our side - the wildcard is not client-specific.
