# ADR-0003: FastAPI on Hetzner with Better Auth sidecar

Status: Accepted

Supersedes: `0003-fastapi-cloud-run_superseded.md`

## Context

The implemented runtime is not Cloud Run. The current app runs a FastAPI backend for data/app/integration routes and a Node.js Better Auth service as a sidecar.

Implemented entrypoints:

- FastAPI: `src/data_platform/api/main.py`
- Better Auth sidecar: `auth-service/server.ts`
- Vite development proxy: `vite.config.ts`

## Decision

Use a self-hosted deployment shape:

- FastAPI serves Sicurre API routes, including `/v1/threats`, `/v1/quarantine`, `/v1/feedback`, `/v1/email/scan`, and `/v1/integrations/cloudflare/*`.
- Better Auth runs as a Node.js sidecar on `127.0.0.1:3005` and exposes `/api/auth/*`.
- The frontend reaches Better Auth through the same origin proxy path `/api/auth`.
- The public API host is the Hetzner server reachable over HTTPS.
- Local development uses separate SQLite files for Sicurre application data and Better Auth; production uses separate Sicurre and `auth` schemas in Neon PostgreSQL.

## Consequences

- Cloud Run cold starts, IAM invoker setup, and Pub/Sub push delivery are no longer part of the app runtime docs.
- Better Auth owns auth/session tables through its own schema while Sicurre API owns workspace, integration, quarantine, feedback, and inference-event tables.
- Operational docs should describe server process management, reverse proxy/TLS, and `.env` configuration instead of Cloud Run deployment.
