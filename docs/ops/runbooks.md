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

## Runbook: A member asks for their account to be erased

**Self-service path.** Settings, Profile, "Supprimer mon compte": the member
types their address, the API tears every connected domain down on Cloudflare,
deletes every workspace row and the Better Auth identity, and the shell signs
out. If Cloudflare refuses (revoked token, zone gone), the erasure stops
before any row is deleted and the member sees the reason; fix the domain
(disconnect it with a fresh token, or delete the stored token) and retry.

**On their behalf.** Console, Cloudflare domains: "Supprimer le compte" on the
domain row, "Supprimer la sélection" after ticking rows, or the form at the
bottom for an account with no connected domain. Every path opens the same
dialog, which lists the accounts and requires the irreversibility box to be
ticked; then `DELETE /v1/admin/accounts` runs once per account and each
refusal is shown with its reason. Refused for the admin's own address.

**The platform's own zone.** `sicurre.com` is both the platform zone (its
catch-all routes to the Sicurre Worker for DMARC and user reports) and the
zone the demonstration account connects. The Worker name derives from the
zone id, so both share one Worker: neither path above may be used for an
account that connected `sicurre.com`, because the teardown would remove the
Worker and stop every inbound mail to the domain. Remove the rows only, in
one transaction, dependants first:

```sql
-- workspace rows, in this order, then the workspace
DELETE FROM app_alert_read WHERE workspace_id = :w;
DELETE FROM app_alert_history WHERE workspace_id = :w;
DELETE FROM app_alert_preference WHERE workspace_id = :w;
DELETE FROM app_security_rule WHERE workspace_id = :w;
DELETE FROM app_quarantine_item WHERE workspace_id = :w;
DELETE FROM app_domain_shield_history WHERE workspace_id = :w;
DELETE FROM app_domain_shield_status WHERE workspace_id = :w;
DELETE FROM app_dmarc_report_summary WHERE workspace_id = :w;
DELETE FROM app_feedback WHERE workspace_id = :w;
DELETE FROM app_reported_email WHERE workspace_id = :w;
DELETE FROM app_support_request WHERE workspace_id = :w;
DELETE FROM app_inference_event WHERE workspace_id = :w;
DELETE FROM app_cloudflare_config WHERE workspace_id = :w;
DELETE FROM cloudflare_integration WHERE workspace_id = :w;
DELETE FROM app_workspace_membership WHERE workspace_id = :w;
DELETE FROM app_workspace WHERE id = :w;
-- identity
DELETE FROM auth."session" WHERE "userId" = :u;
DELETE FROM auth."account" WHERE "userId" = :u;
DELETE FROM auth."verification" WHERE identifier = :email;
DELETE FROM auth."user" WHERE id = :u;
```

The Worker keeps forwarding mail while its integration row is gone (it fails
open when the API refuses the shared secret), and the next onboarding of the
zone redeploys the Worker with a new secret and replaces the routing rule.

**The seeded admin.** The auth sidecar recreates the account named by
`SICURRE_ADMIN_EMAIL` in `deploy/env.auth` on every start when it is missing.
Erase that account only after the last deploy before it is needed again, or
comment the three `SICURRE_ADMIN_*` lines out first. Admin rights come from
`SICURRE_PLATFORM_ADMIN_EMAILS` and return as soon as the address signs up.
