# Production Environment

Sicurre uses split env files in production:

- `.env`: Compose interpolation only. It should not contain application secrets.
- `deploy/env.api`: FastAPI/data-platform runtime secrets.
- `deploy/env.auth`: Better Auth sidecar secrets.
- `deploy/env.alloy`: Grafana Alloy credentials, optional while monitoring is paused.

This is preferable to one global env file because Docker injects `env_file`
values into the target container. A global env would put Cloudflare, DB,
Kaggle, Auth, and Grafana secrets into services that do not need them.

## Local Root `.env`

The root local `.env` is still useful for development and POC work, but it has
more historical/provider variables than production needs. Treat it as a local
developer convenience file, not the production contract.

Current local groups:

- Legacy/cloud experiment keys: `SICURRE_GCP_*`, Databricks, MLflow.
- Data enrichment/model provider keys: Cerebras, Groq, Gemini, Perplexity.
- Data-platform storage and ingestion keys: `SICURRE_RAW_SNAPSHOT_*`,
  PhishTank, CERT-FR, SAP Labs, Common Crawl, historical DB.
- Dataset release keys: `KAGGLE_*`, `SICURRE_GITHUB_ML_*`.
- App/API runtime keys: DB URLs, inference API URL/key, internal API key,
  public API URL, scheduler settings.
- Auth and mail keys: Google OAuth, Better Auth sidecar, Loops templates.
- Observability keys: `GRAFANA_*`; currently paused until Grafana Cloud is back.
- POC-only keys: `SICURRE_POC_*`.

## Production Mapping

Use `deploy/env.compose.example` for `.env`.

Use `deploy/env.api.example` for:

- `SICURRE_DATABASE_URL`
- `SICURRE_DATA_PLATFORM_DATABASE_URL`
- `SICURRE_PUBLIC_API_URL`
- `SICURRE_INFERENCE_API_URL` / `INFERENCE_API_URL`
- `SICURRE_INFERENCE_API_KEY` / `INFERENCE_API_KEY`
- `SICURRE_INTERNAL_API_KEY` / `INTERNAL_API_KEY`
- Cloudflare token/account
- R2 snapshot credentials
- Kaggle dataset publishing credentials
- GitHub ML dispatch token
- scheduler and source cadence settings
- API-side Loops alert templates

Use `deploy/env.auth.example` for:

- `SICURRE_BETTER_AUTH_SECRET`
- `SICURRE_BETTER_AUTH_URL` / `BETTER_AUTH_URL`
- `SICURRE_FRONTEND_ORIGIN`
- `SICURRE_BETTER_AUTH_DB_PATH`
- Loops signup/reset templates
- optional admin bootstrap variables

Use `deploy/env.alloy.example` only when enabling monitoring:

- `GRAFANA_REMOTE_WRITE_URL`
- `GRAFANA_METRICS_USERNAME`
- `GRAFANA_LOKI_URL`
- `GRAFANA_LOKI_USERNAME`
- `GRAFANA_API_TOKEN`

## Names To Prefer

Prefer these canonical names going forward:

- `KAGGLE_API_TOKEN`, not `KAGGLE_KEY`.
- `SICURRE_GITHUB_ML_DISPATCH_TOKEN`, not `SICURRE_ML_DISPATCH_TOKEN`.
- `SICURRE_INFERENCE_API_URL` plus `SICURRE_INFERENCE_API_KEY`; keep
  unprefixed `INFERENCE_*` only as compatibility aliases for existing code.
- `CLOUDFLARE_API_TOKEN`, not app-specific legacy aliases.

## Suspicious Local Keys

The local root `.env` currently has lowercase `email` and `password` keys. They
are not part of the production contract and should not be copied to the server.
