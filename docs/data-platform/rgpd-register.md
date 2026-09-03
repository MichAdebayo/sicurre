# RGPD processing register

Generated from `data_source_system` on 3 September 2026. Every row here is read
from the database rather than maintained by hand, so the register and the
platform cannot drift apart. Regenerate it after adding a source.

Two processing contexts exist and are governed differently. Conflating them is
the most common mistake made about this system, including by its own
documentation.

| | Application | Data platform |
|---|---|---|
| Database | `SICURRE_DATABASE_URL` | `SICURRE_DATA_PLATFORM_DATABASE_URL` |
| Holds | Customer email under scan, quarantine, feedback | The training corpus |
| Subjects | Identified customers and their correspondents | Mostly none |
| Retention | **14 days, enforced** by object-store lifecycle | Declared per source, see below |

## Application processing

**Purpose.** Detect phishing in inbound mail for a protected domain and act on
the verdict — forward, quarantine or reject.

**Legal basis.** Performance of the contract with the subscribing organisation,
and its legitimate interest in securing its own correspondence.

**Categories.** Message content, sender and recipient addresses, subject lines,
delivery metadata, and the verdict with its score.

**Retention.** Quarantined message bodies are held in object storage under a
**14-day lifecycle rule**, provisioned by
`src/data_platform/cli/app/provision_quarantine_lifecycle.py` and enforced by
the storage provider rather than by application code. Verdict records outlive
the body: an event row records that a decision was taken, without retaining
what it was taken on.

**Recipients.** No third party receives message content except the classification
providers, which see a redacted projection bounded by `LLM_MAX_INPUT_CHARS` and
retain nothing. Nothing is sold, shared or used for any purpose beyond
classifying the message it came from.

**Rights.** Deletion of a quarantined item is immediate and irreversible.
Release returns the message to its recipient and records the correction.

## Data-platform processing

**Purpose.** Build and freeze a labelled French corpus for training and
evaluating the classifier.

**Retention is declared per source and is not a deletion schedule.** This
distinction is deliberate and worth stating plainly, because the column name
invites the opposite reading.

A frozen dataset is evidence. Deleting the raw records behind it would break the
lineage that makes a released model reproducible, and would do so to satisfy a
retention limit that exists to protect personal data — of which these sources
carry almost none. As of today the only records past their declared retention
are 829 PhishTank URLs and 18 SAP Labs blog posts: public threat intelligence,
no subjects, no privacy interest in their removal. A purge run against the
declared values would delete exactly the material with no privacy dimension and
leave every record that has one, since those carry the longest retention.

Where deletion has been necessary it has been done deliberately and recorded. On
2 September 2026 the corpus was re-seeded after a length audit found generated
text truncated to 200 characters; 22,562 affected normalized messages and their
88,093 dataset items were archived to R2 and then removed. That is the model:
reviewed, archived first, documented after.

### Sources carrying personal data

| Source | Type | Legal basis | Retention |
|--------|------|-------------|-----------|
| `spam_1` … `spam_5` | file | `legitimate_interest_security` | 365 d |
| `enron_spam` | file | `public_research_dataset` | 365 d |

The `spam_*` sources are exports from the operator's own mailbox and hold real
sender addresses and display names. `enron_spam` is a published research corpus
and is also real employee mail; declaring it as personal data costs nothing and
avoids an obvious question.

**Personal data does not survive normalization.** `redact_pii` removes email
addresses, phone numbers, IBANs, card numbers and postal addresses, and
`redaction_status` records the outcome per message. The raw record retains the
original; the corpus does not.

### Sources carrying no personal data

| Legal basis | Sources | Retention |
|-------------|---------|-----------|
| `public_threat_intel` | `phishtank-online-valid`, `sap-labs-blog`, `sekoia-community-ioc`, `cert-fr-cti` | 30–365 d |
| `public_research_dataset` | `kaggle_french_spamham`, `kaggle_multilingual_spam`, `zefang_phishing`, `cybersectony_phishing_v2`, `data-en-hi-de-fr` | 365 d |
| `public_domain_web_archive` | `common-crawl-bigdata` | 180 d |
| `historical_threat_intel` | `database-historical` and its ten `database/faker/*` and `database/adapted/*` leaves | 365 d |
| `synthetic_reviewed_generation` | the adapted-phishing and CERT-FR lure generators | 365 d |
| `reconstructed_frozen_dataset` | `reconstructed/current_frozen/*` | not set |

Every registered source now declares a legal basis; none is null.

### The reconstructed sources

`reconstructed/current_frozen/generated_pipeline` (2,727 items) and
`reconstructed/current_frozen/native_external` (552) were rebuilt from a
processed copy after the original raw provenance was lost. They are **7.5% of
the corpus**, their upstream origin is documented by reconstruction rather than
by an unbroken ingestion record, and their source names say so. Stating that
limit is stronger than an unqualified provenance claim.

## Sorting and review procedures

| Procedure | Frequency | Mechanism |
|-----------|-----------|-----------|
| Quarantine expiry | Continuous | Object-store lifecycle, 14 days |
| Quarantine purge job | Daily 01:45 | `run_quarantine_purge.py` |
| Language selection | Every normalization | French only reaches the corpus |
| PII redaction | Every normalization | `redact_pii`, outcome recorded per message |
| Deduplication | Every normalization | Unique index on `text_sha256` |
| Corpus review | Per release | Human approval before a dataset is frozen |
| Evaluation-set approval | Per publication | Human review; the gate refuses an unapproved set |

## Known limitations

**Exports are not self-describing.** Frozen CSVs carry `text` and `label` only.
Source attribution lives in `data_dataset_item`, so an export cannot be traced
to its sources without the database. For releases whose index was pruned during
the 2 September remediation, part of that attribution no longer exists — the
content survives in R2, the mapping does not.

**Declared retention has no automated enforcement** in the data platform, by the
decision recorded above. The quarantine TTL is the enforced retention control,
and it governs the data that carries a privacy interest.
