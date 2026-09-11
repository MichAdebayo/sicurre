# Documentation

Everything under `docs/` that is tracked by git is public. A few folders stay
local because they hold third-party material, working notes, or the Word and
PDF versions of the certification reports.

## Public

| Folder | Covers |
|--------|--------|
| [`architecture/`](architecture/README.md) | System context, data design, component design, threat model, monitoring design, accessibility criteria, non-functional requirements |
| [`adr/`](adr/README.md) | Architecture decision records. Superseded ADRs are kept and marked as such |
| [`api/`](api/README.md) | The generated OpenAPI contract and request/response examples |
| [`ops/`](ops/README.md) | Development setup, deployment, logging and monitoring, SLOs, runbooks, incident template |
| [`brand/`](brand/DESIGN.md) | Brand identity and the implementation-facing design system |
| [`data-platform/`](data-platform/rgpd-register.md) | RGPD processing register, generated from the source-system table |
| [`certification/`](certification/README.md) | Incident records, the veille register, the soutenance script, the business specification |

## Local only (ignored by git)

- `simplon/` — the Simplon référentiel and règlement (third-party PDFs)
- `raw_sources/` — third-party papers and CERT-FR bulletins
- `research/` — early surveys and competitive analysis
- `model/`, `deployment/`, `email-intercept.md` — superseded planning notes
- `architecture/notebook-*.md`, `architecture/diagrams/claude/`, `architecture/diagrams/final/` — working notes and rendered diagram exports
- `certification/evaluation-word/` and `certification/screenshots/` — the submitted reports (Word and PDF) and the raw captures they use

If a local document needs to be published, remove its ignore rule first and
review it for personal data, hostnames and credentials before committing.
