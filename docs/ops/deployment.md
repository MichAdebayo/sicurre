# Deployment

## Environments
- dev: personal testing
- staging: beta users
- prod: paying users

## Services
- `sicurre-api` (FastAPI)
- `auth-service` (Better Auth Node.js sidecar)
- `phishing-api` or classifier adapter (model inference)
- `dashboard` / `src/app` (React + Vite production app)
- Cloudflare Email Routing and Email Worker (inbound mail runtime)

## Secrets
Store in the deployment environment or host secret store:
- Better Auth secret
- Neon DATABASE_URL (connection string with pooler endpoint)
- SQLite path for local/dev runtime
- Cloudflare account, zone, and API token values
- Worker shared secret (`X-Sicurre-Secret`)
- API keys for internal calls

## CI/CD (high-level)
- PR → run tests + lint + OpenAPI validation
- Merge to develop → deploy staging
- Tag/release → deploy prod
