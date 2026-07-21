# ML provenance integration contract

This contract connects Sicurre-ML training and promotion workflows to Sicurre's
data-platform lineage store. MLflow remains authoritative for full metrics and
artifacts; Sicurre persists the bounded cross-repository identities required to
audit a candidate, its evaluation, and its deployment outcome.

## Golden-set retrieval

Approved asset:

- version: `golden-20260719-v1`
- URI: `r2://sicurre-golden-evaluation-dataset/golden.jsonl`
- bucket: `sicurre-golden-evaluation-dataset`
- object key: `golden.jsonl`
- SHA-256: `bc329213cacddab409a63deb9d663e593351b6e740a45cdada4c201e3beea346`
- content: 60 French JSONL records (25 phishing, 25 legitimate, 10 spam)

Sicurre-ML stores these GitHub Actions secrets:

- `R2_EVALUATION_ACCESS_KEY_ID`
- `R2_EVALUATION_SECRET_ACCESS_KEY`
- `R2_EVALUATION_ENDPOINT`
- `R2_EVALUATION_BUCKET_NAME` with value `sicurre-golden-evaluation-dataset`

The endpoint is the account's S3 endpoint and the S3 region is `auto`. The
credential must have Cloudflare R2 **Object Read only** permission and be
restricted to the dedicated evaluation bucket. The workflow performs `GetObject` for
the exact key above and must reject the download unless its computed SHA-256
matches the approved checksum. It must not discover a golden set by listing for
the newest key.

The dedicated bucket and Object Read only token provide bucket-level least
privilege. Sicurre-ML has no credentials for training or raw-snapshot buckets
and performs no list operation.

## Callback authentication

Base URL: `https://sicurre.com`

Every callback sends:

```http
Authorization: Bearer <SICURRE_INTERNAL_API_KEY>
Content-Type: application/json
```

The Sicurre-ML repository stores the bearer value as the GitHub Actions secret
`SICURRE_INTERNAL_API_KEY`. Sicurre API receives the same value through its
server environment. `SICURRE_CALLBACK_BASE_URL` may be a repository or
environment variable because it is not secret. Secret values must never be
placed in workflow payloads, logs, manifests, or `relay.md`.

All callback timestamps are RFC 3339 values. All identifiers used as
idempotency keys remain unchanged across retries.

### Candidate registration

`POST https://sicurre.com/internal/ml/candidates`

```json
{
  "model_name": "sicurre-phishing-classifier",
  "semantic_version": "1.0.0",
  "service_source_revision": "0123456789abcdef0123456789abcdef01234567",
  "mlflow_run_id": "<authoritative MLflow run ID>",
  "mlflow_model_version": "<registered MLflow model version>",
  "huggingface_repository": "<owner/repository>",
  "huggingface_revision": "<immutable Hugging Face commit SHA>",
  "training_github_run_id": "<GitHub Actions run ID>",
  "training_dataset_version_tag": "<frozen Sicurre dataset version>"
}
```

The idempotency key is `mlflow_run_id`. An exact replay returns `200` with
`idempotent: true`; conflicting lineage for that key returns `409`. Unknown
training data or invalid input returns `422`. The record is persisted in
`ml_model_version` with stage `candidate`.

### Evaluation result

`POST https://sicurre.com/internal/ml/evaluations`

```json
{
  "candidate_mlflow_run_id": "<candidate MLflow run ID>",
  "incumbent_huggingface_revision": "<immutable incumbent SHA or null>",
  "evaluation_set_version_tag": "golden-20260719-v1",
  "evaluation_set_checksum": "bc329213cacddab409a63deb9d663e593351b6e740a45cdada4c201e3beea346",
  "mlflow_evaluation_run_id": "<authoritative evaluation run ID>",
  "outcome": "passed",
  "metrics": {
    "candidate_weighted_f1": 0.94,
    "production_weighted_f1": 0.93,
    "candidate_phishing_recall": 0.98,
    "production_phishing_recall": 0.97,
    "candidate_legitimate_false_positives": 1,
    "production_legitimate_false_positives": 2
  },
  "evaluated_at": "2026-07-19T18:00:00Z"
}
```

`outcome` is `passed`, `failed`, or `inconclusive`. The idempotency key is
`mlflow_evaluation_run_id`. Exact replay returns `200`; conflicting reuse
returns `409`; unknown lineage, an unapproved set, checksum drift, or invalid
gate data returns `422`. The record is persisted in `ml_model_evaluation`.

### Successful deployment

`POST https://sicurre.com/internal/ml/deployments`

```json
{
  "candidate_mlflow_run_id": "<candidate MLflow run ID>",
  "mlflow_evaluation_run_id": "<passing evaluation run ID>",
  "github_run_id": "<promotion workflow run ID>",
  "approved_by": "<GitHub approver identity>",
  "approved_at": "2026-07-19T18:10:00Z",
  "status": "active",
  "deployed_revision": "<candidate immutable Hugging Face SHA>",
  "failure_reason": null,
  "deployed_at": "2026-07-19T18:12:00Z"
}
```

The idempotency key is `github_run_id`. An active result requires a passing
evaluation and a deployed revision equal to the registered candidate revision.
It persists `ml_model_deployment`, promotes the candidate in
`ml_model_version`, and retires the recorded incumbent.

### Failed deployment or completed rollback

Use the same deployment endpoint and payload. For a deployment that failed
before activation, send `status: "failed"`, omit `deployed_revision` and
`deployed_at`, and provide a bounded `failure_reason`. For a workflow that
restored the preserved incumbent, send `status: "rolled_back"` only after the
rollback and its smoke test succeed; provide the rollback workflow's unique
`github_run_id` and a bounded `failure_reason` describing why rollback was
required. This callback records the operational outcome in
`ml_model_deployment`; the ML workflow remains responsible for moving and
verifying the external production pointers.

Deployment callbacks return `200` for creation or exact replay, `409` for a
conflicting `github_run_id`, and `422` for missing or inconsistent lineage.

## Common responses and retries

Success response:

```json
{"id": "<UUID>", "status": "<record status>", "idempotent": false}
```

- `200`: persisted or safely replayed.
- `401`: missing or invalid bearer token; do not retry automatically.
- `409`: idempotency key reused with different content; stop and reconcile.
- `422`: invalid payload or lineage; stop and reconcile.
- `429`: rate limit exceeded; retry according to `Retry-After`.
- `503`: Sicurre internal callback authentication is not configured; alert and
  retry only within the bounded policy below.

Retry connection failures, timeouts, `408`, `429`, `500`, `502`, `503`, and
`504` at most five times with exponential delays of approximately 1, 2, 4, 8,
and 16 seconds plus jitter. Honor `Retry-After` when present. Use the exact same
payload and idempotency key on every attempt. Never retry `401`, `409`, or `422`
automatically.
