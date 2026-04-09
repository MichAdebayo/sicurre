Implementation Status: Normalization, Adaptation, and Processed Exports

Goal

Phase 2 now has three concrete paths:

1. Direct DB normalization for native French raw records stored in `data_raw_record`.
2. Adaptation for English phishing corpora that should not flow directly into the normalized DB.
3. Processed file exports for the Bloc 1 three-class dataset layout.

Current DB-Backed Normalization Scope

The normalization runner is `scripts/data_platform/shared/normalization/run_normalization.py` and the routing logic lives in `src/data_platform/services/normalization_pipeline.py`.

It currently supports these French-capable source systems already present in the SQLite dev database:

- `database-historical`
- `common-crawl-bigdata`
- `kaggle_french_spamham`
- `kaggle_multilingual_spam`
- `sap-labs-blog`
- `cert-fr-cti`

Normalization rules by source:

- `database-historical`: maps binary labels to `phishing` or `legitimate`.
- `kaggle_french_spamham`: maps `spam` and `ham` to `spam` and `legitimate`.
- `kaggle_multilingual_spam`: same mapping as above, but only the French subset is eligible because the pipeline filters on `detected_language = 'fr'`.
- `sap-labs-blog`: combines subject and body and maps string labels `phishing` or `legitimate`.
- `common-crawl-bigdata`: applies web-cleaning and truncates to 2,500 characters before shared normalization, then routes records into subtype-aware review buckets such as `transactional_legitimate`, `instructional_legitimate`, `promotional_spam`, `awareness_or_report`, `navigation_heavy_holdout`, and `no_window_holdout`.
- `cert-fr-cti`: applies web-cleaning and truncates to 3,000 characters before shared normalization, then routes records into specialized review buckets such as `threat_intel`, `synthetic_lure_candidate`, `procedural_notification`, and `irrecoverable_holdout`; direct normalization remains disabled until a later dedicated persistence design is approved.

Current stage-two implementation notes:

- Source-specific skipped-corpus extraction is now delegated to dedicated services instead of being fully embedded in `normalization_pipeline.py`.
- Review mode can now emit both Markdown and structured JSON artifacts so subtype decisions and derived payload metadata remain reusable in later persistence work.
- CERT-FR derived outputs currently persist as structured review artifacts only; they are intentionally kept out of `data_normalized_message` until a dedicated `data_*` staging design is approved.
- The next-processing lane is now formalized as a stage-two routing matrix with four actions per subtype or quality gate: `promote`, `adapt`, `extract_signals_only`, and `archive`.
- Common Crawl instructional and promotional buckets now explicitly feed adaptation, while CERT-FR threat-intel and procedural buckets feed a signal bank rather than direct message writes.
- Historical specialized rows are split between repair-and-rewrite candidates and dead-holdout archive candidates based on the quality gate reason.
- A downstream artifact builder now materializes those routing decisions into three no-write outputs: an adaptation queue, a signal bank, and an archive manifest.
- The adaptation queue can now be converted into prompt-ready rewrite jobs for reviewed sampled records.
- Those rewrite jobs can now be executed into deterministic no-write draft subject/body outputs, each with a heuristic review state: `usable`, `needs_prompt_tuning`, or `drop`.
- Usable rewrite drafts can now be exported into reviewed candidate corpus rows in JSON, Markdown, and CSV form without touching the DB.
- The CERT-FR signal bank can now be condensed into family, theme, and IOC summaries and then converted into grouped phishing-synthesis scenarios for later prompt-driven generation.
- Those CERT-FR synthesis scenarios can now be converted into deterministic phishing draft outputs, again in no-write mode, before any reviewed export or persistence decision.

All normalized DB writes now create a `DataProcessingRun`, stamp `started_at`, `finished_at`, and `normalized_at`, and skip duplicate normalized texts using the same `text_sha256` uniqueness rule enforced by the schema.

Sources Reserved For Adaptation Instead Of Direct DB Normalization

These sources are intentionally not part of the direct French normalization pipeline:

- `enron_spam`
- `cybersectony_phishing_v2`
- `data-en-hi-de-fr`
- `zefang_phishing`
- `phishtank-online-valid`

The English phishing path is implemented by `scripts/data_platform/datasets/generation/generate_adapted_fr_phishing.py`, backed by `src/data_platform/services/adaptation.py`.

Processed Export Path

The processed three-class export builder is `scripts/data_platform/datasets/preparation/process_restructure_data.py`.

It assembles:

- real French phishing exports
- adapted phishing exports
- synthetic phishing exports
- phishing URL exports
- real French spam exports
- real French legitimate exports
- synthetic French legitimate exports

`scripts/data_platform/datasets/preparation/merge_splits.py` is the follow-on step that merges processed outputs into train, validation, and test splits.

Make Targets For This Stage

The Makefile now exposes the processing-stage entry points:

- `make normalize`
- `make normalize-dry`
- `make normalize-common-crawl`
- `make normalize-db-historical`
- `make normalize-kaggle-fr`
- `make normalize-kaggle-multilingual`
- `make normalize-sap`
- `make normalize-certfr`
- `make adapt-phishing`
- `make synthetic-data`
- `make restructure-processed`
- `make dataset-splits`

Verification Notes

- The dev DB currently contains raw records for all six French-capable normalization sources listed above.
- The new skipped-corpus implementation is currently validated in no-write mode through subtype-filtered route reviews and focused unit tests.
- A dedicated routing-matrix builder now turns the live review artifacts into a concrete downstream policy for non-promotable samples.
- A dedicated downstream builder now emits `stage-two-adaptation-queue.json`, `stage-two-signal-bank.json`, `stage-two-archive-manifest.json`, and a Markdown summary from the live review artifacts.
- Dedicated follow-on builders now emit `stage-two-rewrite-jobs.json` and `certfr-signal-summary.json` from those downstream artifacts.
- The rewrite-job layer now also emits `stage-two-rewrite-drafts.json` and `stage-two-rewrite-drafts.md`, which contain actual draft outputs plus review-state scoring.
- The reviewed export layer now emits `stage-two-reviewed-export.json`, `stage-two-reviewed-export.md`, and `stage-two-reviewed-export.csv` for corpus review before any DB persistence decision.
- The CERT-FR synthesis layer now emits `certfr-synthesis-inputs.json` and `certfr-synthesis-inputs.md` as grouped phishing-generation scenario inputs.
- The CERT-FR draft layer now emits `certfr-generated-drafts.json` and `certfr-generated-drafts.md` as concrete phishing-email candidates derived from those scenarios.
- The local arm64 environment is now able to run the normalization review commands and focused pytest validation.