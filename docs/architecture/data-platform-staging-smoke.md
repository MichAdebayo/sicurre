# Data Platform Staging Smoke Test

The staging smoke test is prepared but not run by default. It builds a dedicated
data-platform API container, applies the current Alembic schema to an isolated
SQLite database inside the container, starts FastAPI on port `8001`, then runs a
one-shot smoke container against it.

Run it when ready:

```bash
make data-platform-staging-smoke
```

The smoke verifies:

- `/health` returns successfully.
- `/openapi.json` is exposed.
- `/v1/data/sources?limit=1` and `/v1/data/datasets?limit=1` can be reached.
- OpenAPI still contains the data publish routes and the internal
  `/v1/email/scan` classification bridge used by the Cloudflare Worker.

The compose file sets `SICURRE_AUTH_ENABLED=false` because this test is for
container boot, schema readiness, and route wiring. It is not a Better Auth or
customer app authorization test.

Container files live at the repository root:

- `Dockerfile.data-platform`
- `docker-compose.data-platform-smoke.yml`

The full app stack smoke lives beside it:

- `Dockerfile.app`
- `docker-compose.app-smoke.yml`
