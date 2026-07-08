# Data Platform Cadence

## Decision

Source ingestion cadence and training-publication cadence are intentionally
decoupled.

Source cron jobs collect data at the frequency that makes sense for each
upstream source. A separate dataset release job decides when accumulated,
validated records should become a new frozen training dataset and be published
to Kaggle.

## Why

The five parent data-source categories do not update at the same speed:

| Parent source | Child source examples | Collection cadence |
|---|---|---|
| API | PhishTank | daily, because the feed changes frequently |
| File | R2 file dropzone | daily or operator-triggered, because source files are event-driven |
| Scraping | CERT-FR CTI | weekly or monthly, because relevant advisories are less frequent |
| Scraping | SEKOIA Community IOC | weekly by default, daily during active phishing-campaign monitoring |
| Database | generated external threat feed | weekly/monthly, because it is controlled by us |
| Big data | Common Crawl | monthly, because extraction is heavier and slower |

Training should not fire every time one source changes. It should run only when
the curated dataset has enough validated delta to justify a new model-training
version.

## Runtime Shape

1. Source cron jobs write raw objects and raw records.
2. Normalization and annotation promote only usable records.
3. Dataset build creates a frozen version from validated normalized messages.
4. Dataset export serializes train/val/test artifacts.
5. Dataset publish pushes the version to Kaggle.
6. Publish dispatches the ML repository training workflow through GitHub
   Actions `workflow_dispatch`.

```mermaid
flowchart LR
    A["Source-specific cron jobs"] --> B["Raw objects and raw records"]
    B --> C["Normalization and annotation"]
    C --> D["Monthly dataset build"]
    D --> E["Export train/val/test"]
    E --> F["Kaggle dataset version"]
    F --> G["GitHub workflow_dispatch"]
    G --> H["ML retraining"]
```

## Production Scheduler Recommendation

When deployed as a separate container, the data platform should own its own
scheduler. The application container should not run ingestion jobs.

Recommended production cadence:

- `phishtank`: daily
- `file`: daily, plus manual operator run when a new file is dropped
- `sekoia`: weekly by default; daily during active phishing campaign monitoring
- `certfr`: weekly
- `database_historical`: monthly
- `common_crawl`: monthly with resumable checkpoints
- `dataset_release`: monthly after all selected source jobs, normalization, and
  annotation complete successfully

The monthly release should be gate-based:

- latest source jobs must not be failed
- normalized dataset delta must be above a configured threshold
- label distribution must remain acceptable
- train/val/test export must succeed locally before Kaggle publish
- Kaggle publish must succeed before GitHub retraining dispatch

## Local Development

Local work can continue on SQLite while the pipeline is being stabilized. The
current pre-production baseline allows deleting and recreating the local DB
without migration debt. Production deployment can later point the same schema
at PostgreSQL/Neon once the flow is stable.

## Kaggle Placeholder Artifact

The existing single-file Kaggle `train.csv` was a connectivity smoke test, not a
valid training dataset release. It should be superseded by the first real
monthly release containing all expected train/val/test artifacts generated from
the frozen database dataset.
