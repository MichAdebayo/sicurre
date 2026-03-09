# Documentation Visibility Policy

This repository uses a split documentation model:

- Public docs are committed and shared for collaboration.
- Private docs are kept locally and excluded by `.gitignore`.

## Public (committed)

- `docs/architecture/` except `threat-model.md` and `privacy-rgpd.md`
- `docs/adr/` except internal ADRs `0001`, `0006`, and `0007`
- `docs/api/`
- `docs/brand/`
- `docs/model/`
- `docs/research/`
- `docs/README.md`

## Private (local-only, ignored)

- `docs/ops/`
- `docs/architecture/threat-model.md`
- `docs/architecture/privacy-rgpd.md`
- `docs/adr/0001-post-delivery-gmail.md`
- `docs/adr/0006-scope-selection-gmail.md`
- `docs/adr/0007-idempotency-pubsub-history.md`

If a private document needs to be published later, remove its ignore rule first and review for sensitive content before committing.
