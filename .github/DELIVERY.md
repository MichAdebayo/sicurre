# Delivery Workflow

## Branch flow

All implementation work starts on a branch such as `app` and moves through two
pull requests:

```text
app (or another working branch) -> develop -> main
```

CI runs for pull requests targeting `develop` or `main`. After the
`develop -> main` pull request merges, CI runs once more on the exact `main`
merge commit. CD listens only for that post-merge `main` CI run and proceeds
only when it succeeds.

The repeated main CI is intentional: PR CI validates the proposed change;
post-merge CI validates the immutable commit that will be released and
deployed. CD never deploys from a pull-request event.

## Sequential CD

Production delivery runs in this order:

1. Semantic Release analyzes conventional commits and creates the next Git tag
   and GitHub release when a release-worthy change exists.
2. Four container images are built and pushed to GHCR with the semantic tag (or
   immutable commit SHA when no release is generated) and `latest`.
3. Hetzner pulls the selected images, applies the stack configuration, restarts
   services, and reloads the shared Nginx proxy.
4. The deployed app gateway and API must pass health checks.
5. The Sicurre Grafana dashboard is imported and read back for verification.

`workflow_dispatch` remains an operator recovery path. It can rebuild and
deploy a selected image tag, but it does not create a semantic release.

## Commit convention

Semantic Release uses Conventional Commits:

- `fix:` creates a patch release.
- `feat:` creates a minor release.
- `BREAKING CHANGE:` in the commit footer, or `type!`, creates a major release.
- `docs:`, `test:`, `ci:`, `chore:`, and `refactor:` do not create a release by
  default unless they include a breaking change.

When using squash merge, keep the pull-request title in Conventional Commit
format so the resulting commit remains release-readable.
