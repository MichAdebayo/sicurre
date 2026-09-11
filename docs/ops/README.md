# Operations

How Sicurre is set up, deployed and watched in production.

| Document | Use it for |
|----------|------------|
| [development-setup.md](development-setup.md) | Tooling versions, database setup, running the stack locally, the CI jobs and how to run them locally, the delivery chain |
| [deployment.md](deployment.md) | Environments, services, secrets, CI/CD and the host layout |
| [logging-monitoring.md](logging-monitoring.md) | The metrics and logs actually emitted, the Grafana dashboards and alert rules, and which controls are declared but unverified |
| [slo-sli.md](slo-sli.md) | Service objectives and the indicators that measure them |
| [runbooks.md](runbooks.md) | Runtime incident procedures |
| [bloc1-sql-runbook.md](bloc1-sql-runbook.md) | Bloc 1 SQL evidence, import steps and baseline execution commands |
| [incident-postmortem-template.md](incident-postmortem-template.md) | The template every incident record under `docs/certification/incidents/` follows |
| [loops-templates.md](loops-templates.md) | Transactional e-mail templates (Loops) and their variables |

Host provisioning, Nginx, Alloy and Grafana provisioning notes live under
`deploy/`.
