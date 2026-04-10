# Data Platform Scripts

This folder is organized by source and by pipeline phase so source-specific recovery workflows do not get mixed with shared tooling.

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
- Keep scripts in this tree limited to orchestration, CLI wiring, manual recovery entrypoints, or no-write investigative/probing workflows.
- If a script starts owning network fetch logic, parsing, retry policy, or persistence rules, move that logic back into `src/` and let the script call it.
- Keep source-specific manual recovery workflows under the relevant source folder.
- Put reusable cross-source builders in `stage_two/`, not under `common_crawl/` or `certfr/`.
- Automated steady-state runners should stay distinct from one-time manual recovery scripts.

## Current Common Crawl phases

- `common_crawl/extraction/run_common_crawl.py`: upstream Common Crawl extraction into R2.
- `common_crawl/ingestion/run_bigdata_ingestion.py`: steady-state latest-parquet ingestion.
- `common_crawl/ingestion/run_bigdata_merged_ingestion.py`: one-time manual merged ingestion of the latest two `fr_usable` parquets.
- `common_crawl/evaluation/evaluate_common_crawl_live_source.py`: exhaustive no-write three-class evaluation over live DB raw records.

Implementation note:
- `src/data_platform/extractors/common_crawl_archive.py` owns upstream archive collection and snapshot building.
- `src/data_platform/extractors/common_crawl_ingestion.py` owns downstream ingestion of prepared Common Crawl snapshots into Sicurre lineage tables.