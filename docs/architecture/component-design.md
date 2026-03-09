
```md
# Component design (Certification-first architecture)

## Purpose

This document describes the target component architecture for the certification project.

It is intentionally organized around the three required phases:

1. Bloc 1: data collection, storage, and exposure
2. Bloc 2: AI integration and exposure
3. Bloc 3: application integration

The previous version of this document described the final SaaS product runtime only.
That view remains valid, but it is now treated as a downstream layer built on top of a dedicated data platform.

## Architectural principle

Sicurre should be presented as a single platform with two bounded contexts inside the backend:

- Data platform context: ingestion, cleaning, normalization, curation, SQL storage, and REST exposure
- Product runtime context: user auth, inbox monitoring, remediation, audit log, and feedback

For certification purposes, the data platform is the primary architecture for Bloc 1.

The product runtime becomes a second layer that consumes curated data and model services.

## Target component map

```mermaid
flowchart LR
		subgraph Sources[External data sources]
				API[Public REST APIs]
				FILE[Files: CSV / JSON / TXT]
				SCRAPE[Web scraping sources]
				SQLSRC[SQL database source]
				BIGDATA[Big data source]
		end

		subgraph DataPlatform[Bloc 1 - Data platform]
				INGEST[Ingestion jobs\nPython scripts / scheduled jobs]
				NORM[Cleaning and normalization pipeline]
				DATAAPI[Sicurre API - Data domain\nFastAPI REST]
				DB[(PostgreSQL / SQLite)]
		end

		subgraph AIPlatform[Bloc 2 - AI services]
				TRAIN[Training and evaluation pipeline]
				MODELAPI[Phishing API / Classifier]
				MLFLOW[Metrics / experiments / model registry]
		end

		subgraph AppLayer[Bloc 3 - Application]
				APPAPI[Sicurre API - App domain\nFastAPI REST]
				STREAMLIT[POC Dashboard]
				REACT[Production dashboard]
				LISTENER[Gmail listener]
		end

		API --> INGEST
		FILE --> INGEST
		SCRAPE --> INGEST
		SQLSRC --> INGEST
		BIGDATA --> INGEST
		INGEST --> NORM
		NORM --> DATAAPI
		DATAAPI <--> DB
		DATAAPI --> TRAIN
		TRAIN --> MLFLOW
		TRAIN --> MODELAPI
		MODELAPI --> APPAPI
		DB --> APPAPI
		STREAMLIT --> APPAPI
		REACT --> APPAPI
		LISTENER --> MODELAPI
		LISTENER --> APPAPI
```

## Bloc 1 components

### 1. Source connectors

- Role: retrieve data from the mandatory source categories required by the certification
- Supported source types:
	- public REST API
	- data files
	- web scraping
	- SQL database source
	- big data source
- Current evidence in the repository:
	- API: PhishTank
	- files: CSV and TXT corpora
	- scraping: CERT-FR and other web sources
	- SQL source: SQLite notebook proof of concept
	- big data: BigQuery and Common Crawl work

### 2. Ingestion jobs

- Role: collect source payloads and register each execution as an ingestion run
- Responsibility:
	- fetch data
	- persist source metadata
	- store raw payload snapshots or references
	- extract first-level records
- Delivery form for certification:
	- Python scripts or scheduled jobs
	- documented parameters, logs, and outputs

### 3. Cleaning and normalization pipeline

- Role: transform raw records into reusable NLP-ready normalized messages
- Responsibility:
	- HTML stripping
	- Unicode normalization
	- language filtering
	- PII redaction
	- deduplication
	- class normalization
	- provenance preservation
- Existing groundwork already lives in the data processing scripts and notebooks

### 4. Sicurre API, data domain

- Role: expose curated data through a documented REST API
- Scope:
	- sources
	- ingestion runs
	- normalized messages
	- annotations
	- datasets and splits
- Security expectations:
	- authentication for write endpoints
	- authorization by role in later phases
	- rate limiting on public endpoints

### 5. Relational database

- Target database for MPD: PostgreSQL
- Development and CI compatibility: SQLite through the same ORM layer
- Role:
	- store lineage from source to curated message
	- support CRUD on curated entities
	- support auditability and RGPD retention rules

## Bloc 2 components

### 6. Training and evaluation pipeline

- Role: consume curated datasets from the data platform and produce versioned models
- Inputs:
	- dataset versions
	- train/validation/test split metadata
	- annotation labels
- Outputs:
	- model artifact
	- metrics
	- evaluation reports

### 7. Phishing API / classifier service

- Role: expose the trained model through a dedicated REST API
- Responsibility:
	- 3-class classification
	- confidence scoring
	- auxiliary signals such as URL and authentication heuristics
- Constraint:
	- stateless service
	- no direct database access in deployed product architecture

### 8. Model observability layer

- Role: monitor model performance and service behavior
- Measures:
	- latency
	- verdict distribution
	- feedback drift
	- evaluation metrics by version

## Bloc 3 components

### 9. Sicurre API, application domain

- Role: expose user-facing product functionality
- Responsibility:
	- auth integration
	- user settings
	- threat log
	- feedback
	- restore and remediation endpoints

### 10. Gmail listener

- Role: receive push notifications, fetch message changes, call the classifier, then call the app domain to persist audit results
- Constraint:
	- idempotent processing is mandatory
	- no direct database access

### 11. POC dashboard

- Role: demonstrate the end-to-end flow during evaluation
- Candidate technology:
	- Streamlit for fast demonstration
- Constraint:
	- consumes the API only

### 12. Production dashboard

- Role: future SaaS interface for users
- Candidate technology:
	- React/TypeScript
- Constraint:
	- consumes the API only

## Certification-oriented interface contracts

### Source connectors -> ingestion jobs

- Pull or receive source data
- Emit structured run metadata

### Ingestion jobs -> data domain API

- Register:
	- source systems
	- ingestion runs
	- raw objects
	- raw records

### Normalization pipeline -> data domain API

- Create or update:
	- normalized messages
	- annotations
	- dataset versions

### Data domain API -> training pipeline

- Read-only access to curated datasets and split definitions

### Classifier -> application domain API

- Write threat log entries and remediation outcomes through an internal contract

## Deployment boundaries

### Certification target

- One backend codebase is enough
- One relational database is enough
- Separate the platform by modules, not by premature microservices

### Recommended split inside the backend

- Data domain module
- Model domain module
- Application domain module

### Production constraint preserved

- In deployed runtime architecture, only the Sicurre API owns the database connection
- Gmail listener and classifier remain separate compute services and communicate over HTTP

