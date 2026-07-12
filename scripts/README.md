# Repository Scripts

The root `scripts/` directory is committed intentionally. These files are
operator and automation entrypoints around reusable code in `src/`; they are
not disposable local scratch files.

## What must remain tracked

- `scripts/app/maintenance/`: destructive local-only maintenance utilities.
- Other `scripts/app/` files: application migration, administration, and
  Cloudflare recovery utilities referenced by deployment or operator runbooks.
- `scripts/data_platform/publish_latest.py` and `release_preflight.py`: the
  production monthly release entrypoints invoked by `Makefile` and the release
  container.
- `scripts/data_platform/seed_frozen_dataset.py`: deterministic recovery and
  pre-production dataset reconstruction.
- `scripts/deploy/`: idempotent infrastructure provisioning invoked by CI/CD.
- Source audit, investigation, and recovery scripts: tracked for reproducibility
  even when they are not copied into a long-lived service process.

## What does not belong here

Temporary output, credentials, copied datasets, ad-hoc scratch files, and
generated reports remain ignored. Reusable fetch, parsing, retry, and
persistence logic belongs under `src/`; a script should only compose it into an
explicit operator action.

Tests and live smoke checks belong under `tests/unit`, `tests/integration`, or
`tests/e2e`, each split again by `app` and `data_platform` ownership.

Python package directories use underscores, such as `data_platform`, because
they must be valid import names. Hyphenated `data-platform` is suitable for a
container, workflow job, or human-facing label, but not an importable Python
package.
