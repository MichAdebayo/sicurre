# Sicurre

Real-time phishing detection and inbox remediation for French auto-entrepreneurs and TPEs. Classifies emails with a fine-tuned CamemBERTv2 model and automatically moves confirmed phishing to Gmail Trash within 2 seconds of delivery.

## Navigate

| Folder | Contents |
|--------|----------|
| `docs/architecture/` | Goals, system design, data schema, NFRs, threat model, RGPD |
| `docs/adr/` | Architecture Decision Records — why we chose key options |
| `docs/api/` | OpenAPI contract + request/response examples |
| `docs/ops/` | Deployment, SLOs, monitoring, runbooks, incident templates |
| `docs/brand/` | Brand identity — colors, typography, motion, French UI copy rules |
| `docs/research/` | Competitive analysis, French corpus data sources, tech-stack survey |
| `tasks/` | Execution plan (`TASK_PLAN.md`) and agent lessons (`lessons.md`) |

## Conventions
- Diagrams: Mermaid embedded in Markdown
- ADRs: immutable records; append new ADRs rather than rewriting history
- Security & privacy: assume least privilege, encrypt sensitive data, minimize retention
- Visibility policy: see `docs/README.md`
