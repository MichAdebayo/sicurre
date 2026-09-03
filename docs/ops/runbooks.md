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
