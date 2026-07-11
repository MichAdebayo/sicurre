# API Contracts

Sicurre is API-first, and the API is now documented as a layered platform that follows the certification sequence.

The API surfaces remain organized by runtime responsibility, while planning and milestones are organized by Bloc 0 plus 5 delivery blocs.

## Canonical contract

The source of truth is [openapi.yaml](openapi.yaml).

The contract should track the implemented runtime. If the architecture changes, update
the OpenAPI contract and the runtime docs in the same change.

## API surfaces

The current API contract intentionally exposes three runtime surfaces:

- Data API
- Model API
- Application API

This does not conflict with the 5 delivery blocs.

- the technical survey and POC bloc produces benchmark and feasibility evidence rather than a separate business API surface
- the monitoring bloc primarily adds health, metrics, logs, alerts, and incident evidence rather than a new user-facing resource family

### Data API

Purpose:
Expose the Bloc 1 data platform through CRUD and read endpoints that support source management, ingestion traceability, curated NLP records, and dataset versioning.

Current endpoints:

- `GET /v1/data/sources`
- `POST /v1/data/sources`
- `GET /v1/data/ingestion-runs`
- `POST /v1/data/ingestion-runs`
- `GET /v1/data/raw-records`
- `GET /v1/data/messages`
- `POST /v1/data/messages`
- `PATCH /v1/data/messages/{id}`
- `DELETE /v1/data/messages/{id}`
- `POST /v1/data/annotations`
- `GET /v1/data/datasets`
- `POST /v1/data/datasets`
- `GET /v1/data/datasets/{id}/items`

Primary resources:

- `data_source_system`
- `data_ingestion_run`
- `data_raw_record`
- `data_normalized_message`
- `data_annotation`
- `data_dataset`
- `data_dataset_item`

### Model API

Purpose:
Expose the Bloc 2 classifier service and model catalog.

Current endpoints:

- `POST /v1/model/classify`
- `GET /v1/model/versions`

Primary resources:

- `ml_model_version`
- `ml_model_evaluation`
- `ml_model_deployment`

### Application API

Purpose:
Expose the runtime product operations for authenticated users and the Cloudflare Email
Worker.

Current endpoints:

- `POST /v1/email/scan`
- `GET /v1/auth/session`
- `PATCH /v1/auth/profile`
- `GET /v1/threats`
- `POST /v1/threats/{id}/status`
- `POST /v1/feedback`
- `GET /v1/quarantine`
- `POST /v1/quarantine/{id}/release`
- `POST /v1/quarantine/{id}/whitelist`
- `DELETE /v1/quarantine/{id}`
- `POST /v1/integrations/cloudflare/setup`
- `GET /v1/integrations/cloudflare/status`
- `POST /v1/integrations/cloudflare/verify-token`
- `GET /v1/integrations/cloudflare/list`
- `/api/auth/*` Better Auth sidecar routes

Primary resources:

- Better Auth `user`, `session`, `account`, and `verification`
- `app_workspace`
- `workspace_member`
- `cloudflare_integration`
- `app_inference_event`
- `app_quarantine_item`
- `app_feedback`

## Naming convention

API documentation follows the frozen table prefixes:

- `data_` for Bloc 1 data platform resources
- `ml_` for model lifecycle resources
- `app_` for application runtime resources

## Incremental delivery strategy

Yes, the project is being built incrementally and deliberately.

The sequence is:

1. complete Bloc 0 baseline and governance documentation
2. implement the Bloc 1 data platform backbone
3. complete the Bloc 2 technical survey and proof-of-concept evidence
4. document and implement the Bloc 3 model endpoints on top of curated datasets
5. document and implement the Bloc 4 application endpoints on top of the model and data layers
6. instrument the Bloc 5 monitoring and incident-evidence layer

This means the documentation and endpoints will continue to evolve in a controlled way as the project moves from experimental corpus work to a structured NLP platform and then to a SaaS runtime.

The key rule is that evolution is sequential, not ad hoc.
Each phase extends the documented foundation from the previous one.
