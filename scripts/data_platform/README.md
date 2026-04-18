# Data Platform Scripts

This folder is organized by source and by pipeline phase so source-specific recovery workflows do not get mixed with shared tooling.

`scripts/` is no longer the canonical launcher surface for Make or day-to-day operational commands. Those entrypoints now live under `src/data_platform/cli/`. This tree is reserved for investigation, manual recovery, one-off backfills, audits, and no-write probes.

## Layout

- `common_crawl/`
  - `extraction/`: Common Crawl snapshot collection, R2 upload, and R2 inventory helpers.
  - `ingestion/`: DB ingestion entrypoints plus one-time reset and manual merge helpers.
  - `evaluation/`: no-write Common Crawl review, promotion, and evaluation scripts.
- `certfr/`
  - `generation/`: CERT-FR signal summarization, synthesis input building, draft generation, and generation quality analysis.
  - `review/`: CERT-FR review staging helpers.
- `historical_db/`
  - `ingestion/`: legacy external DB ingestion entrypoints.
  - `setup/`: external DB seeding helpers for historical-source simulation.
- `sap_labs/`
  - `ingestion/`: SAP Labs source ingestion runner.
- `afi/`
  - `extraction/`: AFI scraping helpers.
  - `preparation/`: AFI dataset filtering helpers.
- `datasets/`
  - `external/`: external dataset discovery and fetch helpers.
  - `generation/`: adaptation and synthetic corpus generation scripts.
  - `preparation/`: restructure, extraction, and split-building scripts.
- `shared/`
  - `audits/`: one-off quality audits.
  - `diagrams/`: documentation diagram generators.
  - `inventory/`: inventory/reporting helpers.
  - `normalization/`: shared normalization runner over live DB sources.
- `stage_two/`: cross-source stage-two routing, adaptation, rewrite, and reviewed-export builders.

## Boundary rules

- Put source-facing operational code in `src/data_platform/extractors/` or shared domain logic in `src/data_platform/services/`.
- Keep scripts in this tree limited to investigation, manual recovery entrypoints, one-off backfills, audits, or no-write investigative/probing workflows.
- If a script starts owning network fetch logic, parsing, retry policy, or persistence rules, move that logic back into `src/` and let the script call it.
- Keep source-specific manual recovery workflows under the relevant source folder.
- Put reusable cross-source builders in `stage_two/`, not under `common_crawl/` or `certfr/`.
- Automated steady-state runners should stay distinct from one-time manual recovery scripts.
- Make should call `src/data_platform/cli/` only. `scripts/` should not be a Make entrypoint surface.

## Naming split

- In `src/data_platform/cli/`, use task-oriented entrypoint names grouped by domain, then by parent source family where helpful, for example `cli/ingest/api/phishtank.py` or `cli/datasets/build.py`.
- In `src/data_platform/cron_schedulers/`, reserve `run_<source>_<stage>.py` for scheduler-triggered entrypoints only, grouped by parent source family such as `cron_schedulers/scraping/run_certfr_cti.py`.
- In `scripts/`, reserve verb-first names such as `extract_*`, `inspect_*`, `reset_*`, and `evaluate_*` for manual probes, recovery tools, and no-write workflows.
- If a command belongs in Make or in normal operator usage, promote it to `src/data_platform/cli/` instead of adding another script launcher here.

## Current Common Crawl phases

- `common_crawl/extraction/extract_common_crawl_snapshots.py`: legacy/manual upstream Common Crawl extraction into R2.
- `common_crawl/ingestion/ingest_latest_common_crawl_snapshot.py`: legacy/manual latest-parquet ingestion.
- `common_crawl/ingestion/ingest_merged_common_crawl_snapshots.py`: one-time manual merged ingestion of the latest two `fr_usable` parquets.
- `common_crawl/evaluation/evaluate_common_crawl_live_source.py`: exhaustive no-write three-class evaluation over live DB raw records.

Implementation note:
- `src/data_platform/extractors/common_crawl_archive.py` owns upstream archive collection and snapshot building.
- `src/data_platform/extractors/common_crawl_ingestion.py` owns downstream ingestion of prepared Common Crawl snapshots into Sicurre lineage tables.