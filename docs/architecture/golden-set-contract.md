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

This set is a promotion gate, not a benchmark, so the reason is regression
detection rather than representativeness. Version one could compare a candidate
against the incumbent on business email compromise — supplier fraud, IBAN
substitution, président fraud, e-signature lures — and on nothing else. A
candidate that degraded on administrative impersonation would have passed the
gate unchanged, because the gate contained no record of that decision class.

Administrative impersonation is a decision class the deployed product actually
takes: auto-entrepreneurs file with the DGFiP and pay URSSAF cotisations, so the
runtime classifies these messages in production. A gate that cannot fail on a
decision the product makes cannot protect that decision.

This is a statement about the gate's coverage of decision classes. It is not a
claim that the corpus mirrors the distribution of French phishing, and the set
remains explicitly not a representative customer benchmark.

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

### What this set must not be used for

The gate's value is its independence. It may be used only to compare a candidate
model against the incumbent, as described under promotion below.

It must not be used to tune runtime configuration: fusion stage weights, LLM
provider order or model tier, thresholds, or quantization settings. Those are
service configuration, not model candidates, and iterating any of them against
these 84 records fits the configuration to the gate. The gate then stops being an
independent signal precisely when a genuine regression needs catching.

Runtime configuration is measured against the training dataset's own `test` and
`holdout` splits, or against a disposable benchmark built for that purpose. Those
may be iterated against freely because nothing depends on their independence.

### Known gaps

Every record is plain text with a median body of ~420 characters. The runtime
receives MIME from the Cloudflare Email Worker and canonicalizes HTML before
classification, so a candidate change affecting that path — display text that
disagrees with its href, markup-obscured payloads, tracking and footer noise —
cannot currently fail this gate. That is a coverage gap in the decision classes
the gate can detect, and is the intended subject of a later version.

Review is single-reviewer, so there is no inter-annotator agreement. The set is
synthetic and provisional; it demonstrates reproducible candidate-versus-incumbent
decisions and establishes no real-world performance claim.

### Publication defect to resolve

`publish_evaluation_set` writes through the shared snapshot store, which resolves
to the raw-snapshot bucket (`r2://sicurre-raw/raw-snapshots/evaluation_sets/...`)
rather than to the dedicated evaluation bucket this contract specifies. Version two
was therefore placed in `sicurre-golden-evaluation-dataset` directly after
validation. The CLI should target the evaluation bucket so publication and
consumption address the same store.
