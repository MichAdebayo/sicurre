# Changelog

Versions follow [semantic versioning](https://semver.org). Tags and per-release
notes are generated from Conventional Commits by semantic-release and published
to [GitHub Releases](https://github.com/MichAdebayo/sicurre/releases), which is
the authoritative record. This file summarises the notable changes only.

## [1.37.14] - 2026-09-14

- The dashboard trend chart has its own bar colours: brighter red, orange and
  emerald in light mode instead of the deep text colours, while dark mode keeps
  its shades. Every bar keeps at least 3:1 against the card and its track.

## [1.37.13] - 2026-09-14

- The quarantine preview shows the message as plain text in a scrollable box
  instead of an embedded frame. Nothing in the message is interpreted either
  way, and Chrome no longer paints a blank frame for an instant on every open.
- The dialog backdrop appears and goes at once, without a fade.

## [1.37.12] - 2026-09-14

- Account deletion erases every stored quarantine copy before its rows,
  instead of leaving the raw messages in storage until the 14-day lifecycle
  expired them. A storage failure stops the deletion before any row goes.
- Disconnecting a domain, alone or through account deletion, gives the
  protected address its forward to the verified destination back. Connecting
  had replaced that rule with the Worker rule, so on a zone without a
  catch-all the address was left with no route.
- Settings: account deletion is a clear danger zone with a description and a
  standard-size button; its dialog is wider and lists what the deletion removes.
  The token revoke and domain disconnect confirmations use the shared dialog,
  and the Cloudflare token buttons use the shared button sizes.
- The activation notice on the sign-in form clears once the member signs in or
  out, instead of returning on every later sign-in in the same tab.
- The privacy page describes what account deletion removes.
- Dark mode: the dialog backdrop is a dark dim in both themes instead of the
  near-white on-background token, which washed the page out behind every
  dialog, and the quarantine preview text follows the theme so it stays
  readable on the dark panel.
- The quarantine preview tidies the stored text before display: Windows line
  endings, whitespace-only lines and runs of blank lines no longer turn a short
  message into a long scroll.
- Dark mode red passes WCAG AA: the theme now defines its own error colour,
  as it already did for safe and warning. The light-theme red sat at 2.7:1
  on the dark surfaces, so every phishing badge on the quarantine page failed.
- The sidebar is 264px wide so the workspace status and the analysed e-mail
  count sit on one line.
- The latency SLO alert needs at least 20 gateway requests in its window, like
  the 5xx alert: one slow account deletion on quiet traffic paged it.

## [1.37.11] - 2026-09-14

- A tab left open across a deploy no longer lands on a white screen. When a
  page file from the earlier build is gone, the app reloads once to pick up
  the current build; any other render failure shows a short message with a
  reload button. The app server answers a missing build file with a 404
  instead of the application shell.
- The e-mail verification link no longer loops on a Cloudflare security check.
  The app server followed the auth service's redirect to /login itself, from
  the Hetzner host; Cloudflare Bot Fight Mode challenged that datacenter
  request and the challenge reached the visitor. Redirects now go back to the
  browser.

## [1.37.10] - 2026-09-14

- The production API writes one log line per request again, so Loki shows
  endpoint activity instead of startup lines only. The start command no longer
  switches uvicorn's access log off; Alloy still drops health and metrics
  probes before they reach Loki.

## [1.37.9] - 2026-09-14

- Dialogs no longer flicker. The backdrop is a plain dim that fades in, with
  no blur: Chromium drew the blur only once the fade ended, so the page
  snapped from sharp to blurred on open and back on close. The panel no longer
  fades or scales, which kept the quarantine email preview from showing
  through ahead of it, and closing unmounts at once.

## [1.37.8] - 2026-09-14

- The quarantine page lists held messages newest first on its own, whatever
  order the API returns, and the API test pins its newest-first ordering.
- Deleting a quarantined email asks one short question ("Supprimer cet
  e-mail ?") and confirms with "E-mail supprimé.".

## [1.37.7] - 2026-09-13

- Mail that is not the customer's is delivered untouched, with nothing stored
  or alerted under their workspace: a message whose envelope recipient is
  outside the integration's zone and its subdomains, and Sicurre's own
  notifications, trusted only when Cloudflare's first Authentication-Results
  header records a DKIM pass for mail.sicurre.com. A Loops login link sent to
  michael@sicurre.com had been scanned, quarantined and alerted under vinse.app
  through their shared Worker, and Sicurre's alerts were quarantined as
  phishing.
- Quarantine previews are decoded from the raw MIME when the Worker uploads
  it, instead of keeping the Worker's projection with raw headers and encoded
  bodies. CD rebuilds the previews of held items on each deploy.
- The quarantine cards no longer lift on hover, which flickered under the
  preview dialog's backdrop.
- The API's application logs, scan outcomes and quarantine failures among
  them, reach Loki at INFO.
- The gateway Worker has a platform mode (`SICURRE_SCAN_DISABLED`): it ingests
  DMARC and user reports and forwards everything else unscanned. sicurre.com's
  catch-all runs on its own `sicurre-platform-gateway`, so vinse.app no longer
  shares a Worker with the platform; both names are protected from teardown.

## [1.37.6] - 2026-09-13

- A domain disconnect or account erasure never deletes a Cloudflare Worker that
  another integration uses or that is on the protected list
  (`SICURRE_PROTECTED_WORKER_NAMES`, default `sicurre-gw-9e622bde`). Read on
  Cloudflare: vinse.app and sicurre.com share one account, both vinse.app
  integrations use that Worker, and the sicurre.com catch-all routes the
  platform's own mail to it, which the vinse.app catch-all cannot reveal.
- The dashboard's security score shows a placeholder while it loads and
  "Note indisponible" in normal-size text only when no grade comes back; it
  used to print that text in the 48 px grade font after every sign-in. The
  shield status queries its two blocklists at the same time.
- No text is forced into capitals any more: the quarantine count badge, the
  KPI and security score labels, the connection status badge, the alert rule
  type badge, the landing page label and the `app-label-tiny` style.
- The admin console names the `revoked`, `pending_verification` and
  `provisioning` statuses in the interface language, and its delete actions
  keep their red on hover.
- nginx: a default HTTPS server refuses, during the TLS handshake, any
  connection whose host name matches no vhost, such as a scan of the server's
  IP. CD installs it with `sicurre.com.conf`, restores the previous files if
  `nginx -t` rejects them, and checks that sicurre.com still answers and that
  an unknown name is refused.

## [1.37.5] - 2026-09-13

- Authenticated API requests do less before their own work. Every request
  wrote the workspace membership and ran two backfill updates; the membership
  is now written only when the name or address changed, and the backfill runs
  once, when the workspace is created. Measured on a local copy with the same
  requests: the dashboard's four calls go from 25 SQL statements to 14 and the
  admin console's two from 26 to 11. On the production database each
  statement is its own transaction and connection check.
- The admin overview reads its ten counts in one statement and runs its six
  lists concurrently.
- The session reply names the domain the dashboard opens on, so after
  sign-in the dashboard loads its figures without waiting for the domain
  list. The other domain pages still wait for the list.
- Data fetched in the last minute is reused when an admin page is revisited
  (30 seconds for the dashboard figures and recent threats), the admin Refresh
  button spins only when clicked, and opening the console loads every admin
  tab's code at once, each page imported once.
- Sessions are still revalidated with Better Auth on every request, as the
  non-functional requirements state; no session cache was added.
- `make test-backend` and `make test-frontend` run each suite on its own.

## [1.37.4] - 2026-09-13

- The operational test panel no longer shows a status pill. "Prêt" repeated
  the enabled "Tester l’alerte" button, and "Actif" repeated the running block
  with its countdown and stop button. When tests are turned off on the server,
  "Désactivé par configuration" now sits beside the greyed-out button, the one
  place the reason was otherwise missing.

## [1.37.3] - 2026-09-13

- The dashboard's four KPI cards show a quiet placeholder bar while their
  figures load. Since 12 September they printed "Chargement" in the 32 px
  figure font after every sign-in, because signing out also clears the cached
  figures; the loading label is kept for screen readers.
- Deleting one's own account is one button in Settings, Profile. The address
  is typed in a short dialog, the button shows the deletion in progress, and
  the landing page confirms "Compte supprimé." once the session is closed. The
  session used to be discarded the moment the API answered, which dropped the
  member on the landing page with no message.
- The console asks once, in a short dialog with no checkbox, and confirms the
  deletion with a notification. The signed-in admin's own row has no delete
  action, and the API's refusals read in French.
- "Supprimer définitivement" is now "Supprimer".

## [1.37.2] - 2026-09-13

- A disconnect never deletes the Worker a zone's catch-all sends mail to, and
  keeps it when the catch-all cannot be read. On sicurre.com that Worker
  receives Sicurre's DMARC reports and the emails users report.
- A disconnect of sicurre.com keeps `dmarc@sicurre.com` in the domain's own
  DMARC record, so the platform keeps receiving its aggregate reports.
- The 1.37.1 erasure guard is withdrawn. It assumed the platform and the
  demonstration client shared one Worker on sicurre.com; Cloudflare shows two.
  Erasing an account tears every domain down again, through the same guarded
  disconnect, so the client Worker and rule no longer stay behind.

## [1.37.1] - 2026-09-13

- Erasing an account no longer tears down the platform's own zone on
  Cloudflare. `sicurre.com` is both the platform's mail zone and the zone the
  demonstration account connects, and both share one Worker: the erasure now
  deletes that zone's rows, keeps its Worker and routing rule, and logs a
  warning. The zone is read from the report mailbox setting. Every other zone
  is still torn down first.

## [1.37.0] - 2026-09-13

- A member can erase their account from Settings, Profile, by typing their
  address again: connected domains are torn down on Cloudflare, every
  workspace row and the Better Auth identity are deleted in one pass, and the
  session closes. A Cloudflare refusal stops the erasure before any row goes.
- The console's Cloudflare domains page is a table: domain, owner, status,
  update date, a checkbox per row and a delete action. A platform admin can
  erase one account from its row, several from the selection, or one with no
  domain by address; every path opens the same alert dialog, which lists the
  accounts, states that the action is irreversible and needs an explicit
  acknowledgement before the cascade runs. Refusals are reported per account.
  The admin's own account is refused there and goes through their settings.
- The RGPD register records the right to erasure with what outlives an
  account, and the runbooks gain the erasure procedure, including the one
  account that shares the platform's own zone and must be removed by rows only.

## [Unreleased] - 2026-09-12

Deployed from `main` without a version tag: refactor commits do not bump the
version.

- The landing-page animation delivers every email once. The envelope's timers
  restarted on each parent render, so the arrival stage never ran: messages
  piled up, bins never bounced and the scanner stayed lit. Found by the new
  animation tests; the handlers are now read through a ref.
- The front files that had no test have one: 105 new Vitest tests, whole-tree
  line coverage from 44% to 64%.
- The Vitest coverage gate measures the whole front. It used to gate seven
  hand-picked files at 90%; it now counts every file under `src/app` plus the
  auth sidecar and the container server, tested or not. With 300 more tests on
  the API client, the routes, the login, the top bar, the Turnstile widget and
  the Cloudflare integrator, the front measures 96% lines, 95% statements,
  91% branches and 94% functions (13 September 2026); the floors are 90, 90,
  85 and 90.
- The Cloudflare connection checklist dismisses itself once provisioning
  completes and tells the settings page. Its completion timer was cleared by
  its own effect re-running, so the checklist stayed on screen and the page
  never refreshed. Found by the new integrator tests.
- Starting a synthetic exercise is limited to 10 per hour (was 2), stopping
  one to 12 per hour (was 6), so a rehearsal plus the defence no longer trips
  the limit. The admin panel names the limit when it is hit instead of the
  generic failure sentence, and a failed action no longer stays on screen
  when the confirmation is opened again.
- The request stats carry meaning in their colour. The live rate turns yellow
  at 5 req/s and red at 10 req/s, the rate at which the scan route refuses
  more than 600 requests per minute per client; the count over the selected
  range carries no colour, since a count has no wrong value. Both had been
  painted by Grafana's default scale, which turned a seven-day count red.
- The Application Health dashboard says what its request stat means. "Live
  Request Rate" is now "Request Rate (last 5 minutes, now)", with three
  decimals, and a new "Requests in Selected Range" stat counts user requests
  over the time range picked at the top of the dashboard, the number that
  belongs next to the seven-day traffic graph.
- The synthetic operational exercises alert within about a minute of the click
  instead of one and a half to four. The three synthetic rules fire on their
  first true evaluation (no pending period), evaluate in their own 30 s group,
  and their notification route waits 10 s instead of 30 s. Real alert rules and
  their thresholds are unchanged. Measured on 12 September 2026 before the
  change: firing email 1 min 30 s after the click, resolved 3 min later; the
  two emails were 3 minutes apart in Gmail even though a mail client showed
  them together.
- A CD dispatch that names an image tag is now a rollback: the build job is
  skipped, the deploy job verifies the four images exist in GHCR under that tag
  before touching the host, and the tag and registry owner come from the
  release job. Before this, a tagged dispatch rebuilt the current source and
  pushed it under the requested tag.
- The deploy prunes every unused image, not only dangling ones. SHA-tagged
  images from earlier deploys had filled the 75 GB host disk and blocked a
  deploy at the config copy step.
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
- `routers/app_routes.py` is gone. Its 2,700 lines are now one module per
  concern: `session`, `threats`, `quarantine`, `alerts`, `domain_shield`,
  `dmarc_reports`, `admin` and `operational_exercises` under `routers/`, the
  admin health probes in `services/runtime_probes.py`, and the workspace
  ownership checks in `api/workspace_scope.py`. The connected-domain list joins
  `routers/integrations.py` and is now tagged `integrations` in the OpenAPI
  contract; every other route keeps its path, schema, tag and operation id. Tests were written first for the branches that had none: profile update,
  threat status and feedback failures, the admin overview and health page,
  exercise refusals, every quarantine release refusal, the Domain Shield
  refresh and the DMARC report helpers.
- `routers/integrations.py` is down to the connect, status, disconnect and list
  routes. The background provisioning is `services/cloudflare_onboarding.py`
  and the Domain Shield DNS sync is `services/domain_shield_sync.py`, which the
  provisioning now reuses instead of carrying its own copy of the same DNS
  block. The setup route is an orchestrator over four small helpers with every
  SQL statement kept verbatim; the setup route was covered to 100% first. The
  only contract change is the setup route's description.

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
