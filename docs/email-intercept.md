# Email Intercept Setup (Cloudflare + Hetzner + Sicurre)

This guide shows how to intercept incoming email for a customer domain (example: `vinse.app`), scan with Sicurre, and then forward only clean mail.

## 1. Target Flow

Incoming email
-> Cloudflare MX receives mail for `vinse.app`
-> Cloudflare Email Worker calls Sicurre API (Hetzner)
-> Sicurre returns verdict (`clean`, `spam`, `phishing`)
-> Worker forwards clean (or clean+spam) mail, rejects/drops phishing

## 2. Decision: Manual Setup vs Integrator

- Manual setup is the fastest way to go live now.
- Integrator in Settings is the best long-term UX for customers.

Recommended:
1. Go live now with manual setup for your own domain (`vinse.app`).
2. Build a Settings integrator that automates 80-90% of Cloudflare tasks.
3. Keep a short manual confirmation step for mailbox verification and final DNS propagation checks.

## 3. Prerequisites

Before starting, confirm:
- Domain is controlled by you (example: `vinse.app`).
- Domain is delegated to Cloudflare nameservers.
- Sicurre API is publicly reachable on Hetzner over HTTPS.
- You have TLS certs working (Let's Encrypt or equivalent).
- You can create Cloudflare API tokens (for future integrator automation).

## 4. Cloudflare Setup (Dashboard Click Path)

### Step 4.1 - Add / verify domain in Cloudflare

Where:
- Cloudflare Dashboard -> Websites -> Add site (if not already added)

What to do:
1. Add `vinse.app`.
2. At registrar, set nameservers to the Cloudflare nameservers shown.
3. Wait until Cloudflare status is Active.

Watch for:
- DNS status must be Active before Email Routing setup will be stable.

### Step 4.2 - Enable Email Routing

Where:
- Cloudflare Dashboard -> `vinse.app` -> Email -> Email Routing

What to do:
1. Enable Email Routing for the zone.
2. Add destination mailbox(es) where clean email should be forwarded (for example your main inbox).
3. Complete destination verification (Cloudflare sends a verification email; click the verify link).

Watch for:
- Destination mailbox must be verified before forwarding works.

### Step 4.3 - Configure address rules

Where:
- Cloudflare Dashboard -> `vinse.app` -> Email -> Routing rules

What to do:
1. Create either:
   - Catch-all rule (`* @vinse.app`) for full protection, or
   - Selected aliases (`contact@`, `support@`, etc.) for phased rollout.
2. Route to the verified destination mailbox (temporary baseline).

Watch for:
- Catch-all can impact every mailbox; start with selected aliases if needed.

### Step 4.4 - Attach an Email Worker (intercept + decision)

Where:
- Cloudflare Dashboard -> Workers & Pages -> Create Worker
- Then bind it to Email events for `vinse.app`

What to do:
1. Create Worker `sicurre-email-gateway`.
2. Add secret variables:
   - `SICURRE_SCAN_URL` (example: `https://api.sicurre.com/v1/email/intercept`)
   - `SICURRE_SHARED_SECRET` (strong random value)
   - `FORWARD_TO` (verified destination mailbox)
3. Configure worker as email handler for the domain.
4. Worker logic:
   - Parse inbound email metadata/body.
   - POST to Sicurre scan endpoint.
   - If `phishing`: reject or quarantine.
   - If `spam`: forward to spam destination (optional policy).
   - If `clean`: forward to normal destination.

Watch for:
- Ensure worker handles timeouts; if Sicurre is unavailable, choose fail-open or fail-closed policy.

### Step 4.5 - DNS records on `vinse.app`

Where:
- Cloudflare Dashboard -> `vinse.app` -> DNS -> Records

What to do:
1. Use the exact MX records shown by Cloudflare Email Routing UI.
   - Do not guess hostnames; use what Cloudflare generated for your zone.
2. Keep or update TXT records:
   - SPF (`v=spf1 ...`)
   - DKIM (from your sending provider)
   - DMARC (`_dmarc.vinse.app`)

Important:
- MX handles inbound receiving.
- SPF/DKIM/DMARC handle sender reputation/authentication for outbound email.
- If you already send mail via another provider, keep that provider's SPF/DKIM requirements.

Watch for:
- Only one active inbound MX strategy should win.
- If multiple providers publish competing MX records, receiving can be unpredictable.

## 5. Hetzner / Server-Side Setup (Sicurre API)

### Step 5.1 - Create scan endpoint

Create endpoint in Sicurre API, example:
- `POST /v1/email/intercept`

Input should include:
- Envelope sender / recipient
- Headers
- Subject
- Plain body / HTML body
- Optional attachments metadata
- Request signature or shared secret

Output contract:
- `{"verdict":"clean"}`
- `{"verdict":"spam"}`
- `{"verdict":"phishing"}`
- Optional fields: `score`, `reason`, `action`

### Step 5.2 - Protect endpoint

Must do:
- Require HTTPS only.
- Validate shared secret or HMAC signature from Worker.
- Add rate limits and payload size limits.
- Add request timeout budget (for example <= 1.5s target decision path).

### Step 5.3 - Logging and audit

Store:
- Message ID, sender, recipient, verdict, score, action, latency.
- Do not store full bodies by default unless customer opted in.
- Redact PII where possible.

### Step 5.4 - Fallback behavior

Define policy:
- Fail-open: if scan API fails, forward mail (safer for deliverability).
- Fail-closed: if scan API fails, block/defer mail (safer for security).

For SMB customers, fail-open + alerting is usually safer operationally.

## 6. Validation Checklist (End-to-End)

After setup, run these tests in order:
1. Send clean test mail to `user@vinse.app` -> verify delivered.
2. Send obvious phishing sample -> verify rejected/quarantined.
3. Send spam-like sample -> verify your spam policy behavior.
4. Check Cloudflare Worker logs for each message.
5. Check Sicurre API logs for each decision.
6. Confirm latency target and no repeated retries/loops.

## 7. Integrator in Sicurre Settings (Preferred UX)

This is viable and recommended.

### What can be automated

From Sicurre Settings, you can automate:
- Connect Cloudflare account via API token input.
- Discover zones and select customer zone.
- Create/update required DNS records (MX/TXT) through Cloudflare API.
- Create/update routing rules.
- Deploy/update worker script and secrets.
- Run post-deploy health checks and display status.

### What usually still needs user confirmation

- Destination mailbox verification click (email link).
- DNS propagation wait/verification (automatic checks possible, but timing varies).

### Integrator UX flow (recommended)

1. Settings -> Integrations -> Cloudflare -> Connect.
2. User pastes restricted Cloudflare API token.
3. Sicurre lists zones, user selects `vinse.app`.
4. User chooses policy:
   - Protect all mail (catch-all)
   - Protect selected aliases
5. Sicurre provisions DNS + routing + worker automatically.
6. Sicurre shows "verify destination mailbox" step with live status.
7. Sicurre runs smoke tests and marks integration healthy.

### Token scopes needed (minimum)

Create a token with zone-scoped permissions for:
- DNS edit/read
- Workers scripts/routes edit/read
- Email routing edit/read (if exposed in API for your plan)

Always use least privilege and zone-scoped tokens.

## 8. Rollback Plan

If anything breaks:
1. Disable Email Worker binding first (stop filtering logic).
2. Keep Email Routing direct-forward rule active.
3. Revert DNS records only if needed.
4. Re-test inbound delivery.
5. Re-enable worker after fixes.

## 9. Practical Recommendation for Your Case

For `vinse.app` on Cloudflare + Hetzner:
1. Do manual setup once using this document.
2. Confirm real traffic is stable for at least 48 hours.
3. Build the integrator in Sicurre Settings and use it for future customer onboarding.

This gives fastest time-to-value now and best scale path later.
