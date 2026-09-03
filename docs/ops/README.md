# Operations

This folder defines how Sicurre is deployed and operated:
- Deployments (Hetzner-hosted API/app runtime)
- Monitoring/alerting
- SLOs/SLIs
- Runbooks for common failures
- Incident postmortems

Key operational references:

- `runbooks.md` for runtime incident procedures
- `bloc1-sql-runbook.md` for Bloc 1 SQL evidence, import steps, and baseline execution commands


Real-Time Blacklist Lookups (DNSBL RBL Integration)
Real Feed Checks: Wired active domain blacklist lookups against Spamhaus Domain Block List (dbl.spamhaus.org) and SURBL (multi.surbl.org) in the python backend resolver.
