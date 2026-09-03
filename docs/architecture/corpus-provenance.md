# Corpus provenance

Per-source composition of `base-20260903-063230` (45,320 items), read from the
production data platform on 3 September 2026 by the same query the export
writes into each split's `metadata.json`.

## Composition

| Source | Phishing | Spam | Legitimate | Total |
|---|---:|---:|---:|---:|
| `synthetic-generated-adapted-phishing-generator` | 4,860 | 0 | 0 | 4,860 |
| `database/adapted/adapted_en_fr` | 4,535 | 0 | 0 | 4,535 |
| `kaggle_multilingual_spam` | 0 | 637 | 3,803 | 4,440 |
| `database/faker/synthetic_legitimate_medium` | 0 | 0 | 4,000 | 4,000 |
| `database/faker/synthetic_spam_medium` | 0 | 3,990 | 0 | 3,990 |
| `database/faker/synthetic_spam_hard` | 0 | 3,000 | 0 | 3,000 |
| `database/faker/synthetic_legitimate_simple` | 0 | 0 | 2,999 | 2,999 |
| `database/faker/synthetic_spam_simple` | 0 | 2,999 | 0 | 2,999 |
| `database/faker/synthetic_phishing_medium` | 2,979 | 0 | 0 | 2,979 |
| `database/faker/synthetic_legitimate_hard` | 0 | 0 | 2,974 | 2,974 |
| `reconstructed/current_frozen/generated_pipeline` | 2,727 | 0 | 0 | 2,727 |
| `database/faker/synthetic_phishing_simple` | 2,213 | 0 | 0 | 2,213 |
| `database/faker/synthetic_phishing_hard` | 2,012 | 0 | 0 | 2,012 |
| `kaggle_french_spamham` | 0 | 498 | 500 | 998 |
| `reconstructed/current_frozen/native_external` | 0 | 423 | 129 | 552 |
| `sap-labs-blog` | 7 | 0 | 10 | 17 |
| `common-crawl-bigdata` | 0 | 1 | 10 | 11 |
| `synthetic-generated-certfr-lure-generator` | 7 | 0 | 0 | 7 |
| `spam_2` | 0 | 3 | 0 | 3 |
| `spam_3` | 0 | 3 | 0 | 3 |
| `spam_1` | 0 | 1 | 0 | 1 |
| **Total** | **19,340** | **11,555** | **14,425** | **45,320** |

## The number that matters

**Sixteen of the twenty-one sources produce exactly one class.**

Nearly every phishing example comes from a source that emits nothing but
phishing; the same holds for most of the spam and legitimate rows. Only five
sources are mixed, and three of those contribute 31 items between them.

This is the shape behind the finding that the earlier model separated
*provenance* rather than *intent*. A classifier does not need to learn what a
phishing message looks like when the generator that produced it is inferable
from vocabulary, length, punctuation or formatting — source and label are very
nearly the same variable.

It also explains why the golden set is the promotion gate and why held-out
accuracy on this corpus is not: a split of this data leaves the confound intact
on both sides, so a model can score well on the test split by learning the
generators, and a test split drawn from it contains no real phishing at all.

## Real versus generated

| | Items | Share |
|---|---:|---:|
| Synthetic (faker, adapted, lure generators, reconstructed pipeline) | ~33,300 | 73% |
| External corpora (Kaggle, reconstructed native) | ~5,990 | 13% |
| Live feeds (SAP Labs, Common Crawl, dropzone) | 35 | 0.08% |

The live-feed row is the one to read twice. Thirty-five items across three
sources means the corpus is, in practice, a synthetic corpus with a real-data
garnish — which is a statement about what a model trained on it can be expected
to generalise to.

## How this was produced

```sql
SELECT COALESCE(ss.name, 'unattributed') AS source,
       nm.current_label AS label, count(*)
FROM data_dataset d
JOIN data_dataset_item di ON d.id = di.dataset_id
JOIN data_normalized_message nm ON di.normalized_message_id = nm.id
LEFT JOIN data_raw_record rr ON nm.raw_record_id = rr.id
LEFT JOIN data_source_system ss ON rr.source_system_id = ss.id
WHERE d.version_tag = :version
GROUP BY source, label;
```

The joins are `LEFT` so a record whose raw row was removed is counted as
`unattributed` rather than dropped — this release has none. The export runs the
same query and writes the result into each split's `metadata.json`, so a
released dataset carries its own provenance rather than needing this document
to be re-run.
