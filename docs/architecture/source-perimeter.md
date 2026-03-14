# Bloc 1 Source Perimeter

## Purpose

This document is the source of truth for the Bloc 1 source perimeter.

It defines which sources are frozen for Bloc 1, which are included as secondary supporting sources, and which candidates remain outside the frozen perimeter for now.

This document is the main evidence artifact for GitHub Issue `#1`:
`Freeze Bloc 1 source inventory and extraction perimeter`.

## Decision rule

For each source, we specify:

- the source name
- the certification source type it satisfies
- its Bloc 1 status
- the reason for inclusion
- the expected output

## Frozen Bloc 1 perimeter

These sources are part of the committed Bloc 1 perimeter and should be treated as the primary extraction backbone.

| Source | Certification type | Status | Reason for inclusion | Expected output |
|--------|--------------------|--------|----------------------|-----------------|
| PhishTank | API REST | frozen | explicit API evidence for C1, public feed, phishing URL extraction | raw API records and filtered phishing URLs |
| CERT-FR CTI reports | scraping | frozen | official French threat-intelligence source, strong French phishing relevance | scraped report metadata, phishing indicators, extracted text |
| AFI / antifraudintl French scam corpus | scraping | frozen | real-world French scam and phishing content already processed in the repo | raw scraped scam emails and filtered French subset |
| Local CSV/TXT corpora | file | frozen | direct evidence for file-based extraction and aggregation | structured local file imports |
| SQLite/PostgreSQL read-back extraction | SQL database | frozen | explicit database-source evidence for certification | SQL extraction results and documented queries |
| BigQuery | big data | frozen | primary big-data evidence already documented in notebook and task plan | extracted phishing email rows and query evidence |
| Common Crawl | big data | frozen | active big-data exploration path already implemented in notebook and standalone script | extracted web-page text and quality assessment output |

## In-scope secondary sources

These sources remain in scope for Bloc 1, but they do not replace the frozen extraction backbone above.

| Source | Type | Status | Reason |
|--------|------|--------|--------|
| Synthetic French phishing corpus | generated internal dataset | secondary | useful for dataset completion, but not one of the mandatory external extraction families |
| Adapted English-to-French phishing corpus | generated transformation dataset | secondary | useful for corpus enrichment, but distinct from the required extraction source families |

## Candidate sources not yet frozen

These sources may be added later, but they are not required to validate Issue `#1`.

| Source class | Status | Reason |
|-------------|--------|--------|
| additional phishing feeds | candidate | useful for scale, but not needed to prove the current Bloc 1 perimeter |
| additional scraping targets not yet backed by notebook or script evidence | candidate | should only be frozen once extraction and quality are documented |
| additional corpora not yet normalized into the current platform flow | candidate | should be evaluated after the primary perimeter is implemented |

## Explicit exclusions from Bloc 1 perimeter

These are not treated as primary Bloc 1 extraction sources.

| Source | Reason for exclusion |
|--------|----------------------|
| live Gmail production mailbox ingestion | belongs to the application runtime flow, not the certification-facing data platform perimeter |
| live M365 tenant ingestion | same reason as Gmail, and also outside the current delivery focus |
| runtime telemetry and app logs as training data | belongs to monitoring and feedback loops, not the frozen Bloc 1 source perimeter |
| ad hoc manual uploads outside the defined ingestion flow | not stable enough to count as perimeter evidence |

## Closure condition for Issue #1

Issue `#1` can be considered complete when:

- this document is linked from the architecture documentation
- the frozen perimeter is accepted as the Bloc 1 source baseline
- the GitHub issue references this file as its evidence artifact