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

## Runbook: authorise DMARC reporting for a newly onboarded domain

**Do this once per client domain, on `sicurre.com`, right after onboarding.**

Domain Shield adds `rua=mailto:dmarc@sicurre.com` to the client's DMARC record,
which asks receivers to send their aggregate reports to us. That is only half of
what the standard requires. Because the mailbox sits on a different domain from
the record, RFC 7489 §7.1 makes `sicurre.com` publish its consent — otherwise a
receiver that checks is entitled to refuse, and simply will not send the report.

Google and Microsoft both check. Without this record, Sicurre receives reports
only from the receivers that skip the check, so the DMARC page shows a partial
picture of the client's mail and nothing indicates that anything is missing.

Publish on the **sicurre.com** zone, once per onboarded domain:

```
<client-domain>._report._dmarc.sicurre.com   TXT   "v=DMARC1"
```

For a client on `example.com` that is
`example.com._report._dmarc.sicurre.com`. Add a second record for any subdomain
that carries its own DMARC record pointing at us, for example
`mail.example.com._report._dmarc.sicurre.com`.

Verify:

```bash
dig +short TXT <client-domain>._report._dmarc.sicurre.com
```

An empty answer means the authorisation is missing and reports are being
declined. Aggregate reports arrive daily, so allow ~24-48h before judging
whether the change worked.

**Why this is not automated.** The record belongs to the Sicurre zone, not the
client's. Auto-configuration only ever holds a token for the client's zone and
deliberately writes nothing outside it. Automating this would mean giving the
API a second, Sicurre-owned Cloudflare credential with write access to our own
DNS — a meaningful increase in blast radius for a record that changes once per
client. It stays a manual step until that trade is worth making.

**On teardown.** Disconnecting a client withdraws `dmarc@sicurre.com` from their
DMARC record automatically, so they stop reporting to us. The
`_report._dmarc` record on our side is then inert and can be removed at leisure;
leaving it grants no access to anything.
