# Provisional Golden-Set Contract

## Purpose

The Sicurre golden set is an evaluation-only, synthetic, human-reviewed asset.
It demonstrates reproducible candidate-versus-production decisions. It is not a
representative customer benchmark, an SLA claim, or model-training input.

## Version One Composition

- 25 phishing messages
- 25 legitimate but suspicious-looking messages
- 10 spam messages
- French-only examples, matching the Sicurre model and product scope
- No real personal data, credentials, live login URLs, or operational phishing
  infrastructure

Every record is reviewed before publication. The publication command rejects
duplicate IDs, missing review evidence, incorrect class counts, malformed JSONL,
and values outside the production inference envelope.

## JSONL Record

Each line contains:

- `id`: stable `golden-*` identifier
- `subject`, `sender`, `text`: bounded inference inputs
- `expected_label`: `phishing`, `legitimate`, or `spam`
- `language`: always `fr`; publication rejects every other language
- `scenario` and `difficulty`
- `reviewer_rationale`, `reviewed_by`, and `reviewed_at`

Records are sorted by stable ID and serialized canonically. SHA-256 of the
complete JSONL file is the immutable evaluation-set identity.

## Storage And Publication

The asset is stored under the isolated `evaluation_sets/<version>/golden.jsonl`
prefix. It is never placed under `training_dataset`, exported to train/val/test,
or attached to the Kaggle training kernel.

```bash
PYTHONPATH=src uv run --no-sync python -m \
  data_platform.cli.datasets.finalize_evaluation_set \
  --input golden-set-draft.fr.jsonl \
  --output data/local/evaluation_sets/golden-20260719-v1/golden.jsonl \
  --reviewed-by MichAdebayo \
  --reviewed-at 2026-07-19T17:29:21+00:00

PYTHONPATH=src uv run --no-sync python -m \
  data_platform.cli.datasets.publish_evaluation_set \
  --input /path/to/reviewed-golden.jsonl \
  --version-tag golden-20260719-v1 \
  --reviewed-by MichAdebayo \
  --reviewed-at 2026-07-19T17:29:21Z \
  --backend r2
```

The resulting `data_evaluation_set` row records the R2 URI, checksum, counts,
schema version, provenance marker, reviewer, and review time.

The first approved provisional version is `golden-20260719-v1`. It contains 60
French records (25 phishing, 25 legitimate, and 10 spam), is stored in the
dedicated read-only evaluation bucket at
`r2://sicurre-golden-evaluation-dataset/golden.jsonl`,
and has SHA-256 checksum
`bc329213cacddab409a63deb9d663e593351b6e740a45cdada4c201e3beea346`.

## Promotion Policy

Training and production promotion are separate operations. Training publishes
an immutable candidate with its semantic version, source commit, MLflow run and
registry version, Hugging Face repository and immutable commit, and frozen
training-dataset identity. It never advances a production pointer.

Candidate and incumbent are evaluated on the same approved immutable golden
set. The provisional gate has zero tolerance and requires weighted F1 and
phishing recall to be no lower, and legitimate false positives to be no higher.
Because the denominator is identical, comparing the false-positive count is
equivalent to comparing its rate. Latency remains diagnostic evidence in
MLflow rather than an initial blocking gate.

The owner reviews MLflow evidence and provenance, manually dispatches
promotion, and approves the protected GitHub `production` environment. Only a
successful deployment callback moves Sicurre's production state. The previous
model and immutable revision remain recorded for deterministic rollback.

The promotion manifest belongs to the Sicurre-ML evaluation run. Sicurre keeps
the bounded decision snapshot and external identifiers needed to trace it; it
does not duplicate full metrics or artifacts from MLflow. Neither system may
put secrets, raw emails, generated sample text, or user PII in tags or manifests.

## Version Two Composition

`golden-20260816-v2` extends version one rather than replacing it. All 60
version-one records are carried forward unchanged, keeping their identifiers and
their original `2026-07-19` review provenance, and 24 administrative-impersonation
records are added as 12 matched phishing/legitimate pairs.

Composition is 37 phishing, 37 legitimate and 10 spam across 84 French records,
stored at `evaluation_sets/golden-20260816-v2/golden.jsonl` in the dedicated
evaluation bucket with checksum
`448809d4a6c98d115f889887697259c393bfe4e9eccfdb43a01145efe3222387`.

### Why the block was added

Version one is a business-email-compromise corpus: supplier fraud, IBAN
substitution, président fraud and e-signature lures. That focus is right for
TPEs, but the word `impot` appeared zero times across all 60 records while the
DGFiP refund campaign was reaching millions of French households. Auto-entrepreneurs
file with the DGFiP and pay URSSAF cotisations, so administrative impersonation
sits squarely in their threat model.

The block covers DGFiP refunds and arrears, URSSAF cotisations, CPAM/ameli, ANTAI
fines, parcel delivery and customs, CPF, France Travail, professional VAT,
FranceConnect and complementary health insurance. Each fraudulent record is paired
with a legitimate notice from the same institution, so the evaluation measures
discrimination rather than brand-keyword sensitivity: a genuine notice announces
and directs to an official portal, while the fraudulent one collects banking or
identity data through an external link under time pressure.

### Composition rule

Fixed per-class counts are replaced by an invariant. Phishing and legitimate
counts must be equal, so aggregate metrics cannot move through composition alone,
and no class may fall below its version-one floor. The set may grow, but it may
not become unbalanced or lose coverage.

### Known gaps

Median body length remains ~420 characters and every record is plain text. Real
campaigns carry HTML, footers, disclaimers and tracking markup, so length and
markup realism remain untested. Review is still single-reviewer, so there is no
inter-annotator agreement.

### Publication defect to resolve

`publish_evaluation_set` writes through the shared snapshot store, which resolves
to the raw-snapshot bucket (`r2://sicurre-raw/raw-snapshots/evaluation_sets/...`)
rather than to the dedicated evaluation bucket this contract specifies. Version two
was therefore placed in `sicurre-golden-evaluation-dataset` directly after
validation. The CLI should target the evaluation bucket so publication and
consumption address the same store.
