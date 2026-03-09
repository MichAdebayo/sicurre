# API Contracts

Sicurre is API-first, and the API is now documented as a layered platform that follows the certification sequence.

## Canonical contract

The source of truth is [openapi.yaml](openapi.yaml).

Documentation comes before implementation.
If the architecture changes, update the OpenAPI contract first and only then implement the backend.

## API surfaces

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
Expose the Bloc 3 runtime product operations for authenticated users.

Current endpoints:

- `POST /v1/app/remediate/gmail/trash`
- `GET /v1/app/threat-log`
- `POST /v1/app/threat-log/{id}/restore`
- `POST /v1/app/feedback`
- `GET /v1/app/users/me`
- `GET /v1/app/stats`
- `GET /auth/login/google`
- `GET /auth/callback/google`
- `POST /auth/logout`

Primary resources:

- `app_user`
- `app_oauth_token`
- `app_watch_state`
- `app_threat_log`
- `app_feedback`
- `app_session`

## Naming convention

API documentation follows the frozen table prefixes:

- `data_` for Bloc 1 data platform resources
- `ml_` for model lifecycle resources
- `app_` for application runtime resources

## Incremental delivery strategy

Yes, the project is being built incrementally and deliberately.

The sequence is:

1. document and freeze the Bloc 1 architecture, table names, and Data API
2. implement the data platform backbone
3. document and implement the Bloc 2 model endpoints on top of curated datasets
4. document and implement the Bloc 3 application endpoints on top of the model and data layers

This means the documentation and endpoints will continue to evolve in a controlled way as the project moves from experimental corpus work to a structured NLP platform and then to a SaaS runtime.

The key rule is that evolution is sequential, not ad hoc.
Each phase extends the documented foundation from the previous one.
