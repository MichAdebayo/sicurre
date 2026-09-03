# Monitoring validation, 3 September 2026

## Production evidence

One owner-approved, four-minute synthetic exercise was started from `/admin`.
It changed the operational-exercise signal, not customer traffic, email content,
model configuration or service availability. Times below are Paris time (UTC+02).

| Observation | Time | Source |
| --- | --- | --- |
| Exercise started, prefix `6d6eee12` | 13:46:54 | Sicurre production log |
| Rule pending | 13:47:10 | Grafana rule-state API |
| Rule firing | 13:48:10 | Grafana rule-state API |
| Firing email received | 13:48:44 | Connected Gmail mailbox |
| Manual recovery | 13:49:38 | Sicurre production log and admin history |
| Rule normal, signal zero | 13:50:10 | Grafana rule-state API |
| Resolved email received | 13:50:44 | Connected Gmail mailbox |

The verified contact point is `Sicurre Operations`, destination
`michael@sicurre.com`, with resolved notifications enabled. Subjects were
`[FIRING:1] Sicurre controlled operational exercise` and
`[RESOLVED] Sicurre controlled operational exercise`. Earlier messages from the
same day were not counted as evidence for this test.

[Exact evidence window](https://sicurre.grafana.net/d/sicurre-controlled-exercise/sicurre-alert-chain-evidence?from=1788435900000&to=1788436380000).
[ML dashboard](https://sicurre.grafana.net/d/sicurre-ml-runtime/sicurre-ml-inference).

## Corrections and delivery status

ML rules use `service=sicurre-ml`; the previous policy matched only
`stack=sicurre`. Both now reach Operations, with existing thresholds unchanged.
Dashboard provider labels, revision display, stage averages and missing-data
semantics were corrected. Grafana configuration is live.

The new admin panel has one explicitly synthetic action, accessible theme pairs,
confirmation, countdown, stop action, real history and Grafana links. Loading
and errors no longer appear as disabled configuration. Restart restoration and
conditional recovery persistence prevent stale or duplicated recovery state.
These application changes originated on `fix/monitoring-demonstration` and are
now deployed from main. ML source originated on `fix/grafana-runtime-evidence`
and is also deployed from main.

The production log also recorded automatic recovery at 13:50:55 after manual
recovery. This genuine historical defect remains visible in the screenshot.
The conditional update and regression test prevent duplicate logging after
deployment; historical evidence has not been edited.

## Screenshots and verification

Files are in `../screenshots/2026-09-03-monitoring/`:

- `ml-runtime.png`: actual production metrics at desktop width.
- `alert-chain-recovered.png`: actual production signal history and logs.
- `admin-active-light.png` and `admin-active-dark.png`: **local visual fixtures**,
  not production incidents, using the actual component in a 375px-wide container.
  All requests in the fixture are intercepted locally.

Confirmation, active, recovery and error states were checked in both themes.
Contrast regression tests enforce 4.5:1 for the affected token pairs. Targeted
API, UI, authorization and provisioning tests pass. The complete Sicurre
Python unit/integration suite has 1,067 passing tests in CI; the frontend suite has
156 passing tests; the ML unit suite has 264 passing tests. The frontend build
and OpenAPI drift check pass.

CI also verifies 91% core/database coverage and 100% coverage of changed Python
lines, with all gates unchanged.

The isolated real Alloy/Prometheus test also passes against the final public
health query: HTTP success, malformed body, 503, redirect, refused connection,
recovery, stale observations and missing observations. These are local probe
tests, not induced production outages.

The revised ML overview uses four full-sized statistics cards and four charts.
Service health, resources and reliability are separately expandable. Availability
uses Up/Down; stale and unknown observations remain distinct. Light and dark
themes were checked in the actual 919px-wide desktop panel and a 1280px view.

## Certification scope

This is C20 evidence for ingestion, rule evaluation and notification/recovery
delivery. It does not simulate an actual customer outage or independently test
all twelve ML detectors. C21 additionally needs a reproduced defect, diagnosis,
versioned correction and regression verification. The working local POC
injection/restoration demonstrations remain separate evidence.

## ML production deployment

Sicurre-ML main commit `d330bd8c43fc67fccac8d00ce914d259e74bb44b` passed CI
and CD run `33758347061`, including deployment and telemetry validation.
The public `/v1/health` probe now reports HTTP 200 and success 1. Exactly five
probe series are exported. Its Grafana rule is inactive with health `ok`.
Public API, ML scrape, Model and Alloy all display Up. No model artifact changed.

The initial Unknown card appeared because the dashboard was published before
the new probe deployment. It represented absent observations, not an API outage.

Final deployed screenshots: `ml-runtime-final-dark.png` and
`ml-runtime-final-light.png`, each at 1280x720 with diagnostic rows collapsed.
These supersede `ml-runtime.png` for the final overview layout.

## Sicurre deployment and final notification verification

Sicurre main commit `6ed348a24611a6a8cda516bbc0daaf4586c10707` passed CI
`33760581046` and CD `33761471702`, including health checks and Grafana
provisioning. The source followed feature -> app -> develop -> main through
PRs #366/#368/#369, #367 and #370. Both scoped issues #365 and ML #163 closed
automatically. Neither pipeline bypassed its checks.

The deployed admin confirmation and active states were visually verified in
both themes. A second approved four-minute test, `de685404`, then verified the
new scenario-specific subjects. Times below are Paris time (UTC+02).

| Observation | Time | Source |
| --- | --- | --- |
| Start persisted | 15:36:22 | Admin history; log at 15:36:22.822 |
| Pending | 15:38:10 | Grafana rule-state API |
| Firing | 15:39:10 | Grafana rule-state API |
| Firing email received | 15:39:43 | Connected Gmail mailbox |
| Manual recovery persisted | 15:40:04 | Admin history; log at 15:40:05.096 |
| Normal, signal zero | 15:41:10 | Grafana rule-state API and Prometheus |
| Resolved email received | 15:41:43 | Connected Gmail mailbox |

The subjects are `[FIRING] Sicurre API unavailable (synthetic test)` and
`[RESOLVED] Sicurre API unavailable (synthetic test)`. Receipt identifiers are
`1a0677f3d3d8937a` and `1a067810e5a9a226`. The configured destination remains
`michael@sicurre.com`. No customer failure was injected.

After the original expiry time, the production log query contains exactly one
start and one manual recovery in this test window, with no duplicate automatic
recovery. The separate latency and server-error synthetic rules remain Normal.
This verifies delivery for the API scenario; it does not claim every detector
was triggered.

Final production captures:

- `admin-production-confirm-dark.png`, `admin-production-confirm-light.png`
- `admin-production-active-dark.png`, `admin-production-active-light.png`
- `alert-chain-final-active.png`, `alert-chain-final-recovered.png`
- `ml-health-final-dark.png`, `ml-health-final-light.png`

The earlier `admin-active-*` images remain explicitly local fixtures. Use the
`admin-production-*` captures for evidence of the deployed interface.
