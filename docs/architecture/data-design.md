# Data design

## Purpose

This document now separates two distinct but related schemas:

1. the certification-facing data platform schema for Bloc 1
2. the product runtime schema for the SaaS application

The certification schema is the primary source of truth for MCD, MLD, and MPD.
The runtime schema remains necessary, but it is downstream from the data platform.

## Scope of the Bloc 1 data platform

The data platform must prove the following chain end to end:

- collect data from multiple source types
- aggregate and clean the data
- normalize and label usable NLP records
- store lineage in a relational database
- expose the curated data through a REST API

For this reason, the central business object is not the end user account.
It is the curated message dataset derived from heterogeneous sources.

## Merise MCD (conceptual model)

### Conceptual entities

| Entity | Main attributes | Identifiant |
|--------|-----------------|-------------|
| SYSTEME_SOURCE | nom, type_source, description, proprietaire, base_legale, contient_donnees_personnelles, politique_retention, actif | id_source |
| EXECUTION_INGESTION | date_debut, date_fin, statut, mode_declenchement, nb_objets_bruts, nb_enregistrements_bruts, message_log | id_ingestion |
| OBJET_BRUT | reference_externe, type_objet, uri_stockage, hash_contenu, date_collecte, taille_octets, format_source, metadata_source | id_objet_brut |
| ENREGISTREMENT_BRUT | cle_source, contenu_brut, langue_detectee, date_extraction, est_exploitable | id_enregistrement_brut |
| EXECUTION_TRAITEMENT | date_debut, date_fin, version_pipeline, statut, nb_messages_normalises, nb_rejets, rapport | id_traitement |
| MESSAGE_NORMALISE | texte_normalise, hash_texte, langue, categorie_courante, score_qualite, contient_pii, statut_redaction, longueur_texte, date_normalisation | id_message |
| ANNOTATION | label, origine_label, confiance_label, commentaire, date_annotation, valide | id_annotation |
| JEU_DONNEES | nom, version_jeu, usage_cible, date_gel, statut, nb_lignes | id_jeu |
| LIGNE_JEU_DONNEES | split, poids_apprentissage, ordre_ligne | id_ligne_jeu |

### Conceptual associations

- SYSTEME_SOURCE (1,1) - PRODUIT - (0,n) EXECUTION_INGESTION
- EXECUTION_INGESTION (1,1) - COLLECTE - (0,n) OBJET_BRUT
- OBJET_BRUT (1,1) - CONTIENT - (0,n) ENREGISTREMENT_BRUT
- EXECUTION_TRAITEMENT (1,1) - TRANSFORME - (0,n) ENREGISTREMENT_BRUT
- ENREGISTREMENT_BRUT (0,1) - DEVIENT - (0,1) MESSAGE_NORMALISE
- MESSAGE_NORMALISE (1,1) - RECOIT - (0,n) ANNOTATION
- JEU_DONNEES (1,1) - COMPOSE - (1,n) LIGNE_JEU_DONNEES
- MESSAGE_NORMALISE (1,1) - APPARTIENT_A - (0,n) LIGNE_JEU_DONNEES

### Conceptual notes

- `SYSTEME_SOURCE` captures RGPD and governance information at the source level.
- `OBJET_BRUT` represents the collected payload or snapshot.
- `ENREGISTREMENT_BRUT` represents a row, page, message, or extracted item inside a raw object.
- `MESSAGE_NORMALISE` is the reusable NLP unit after cleaning, deduplication, and redaction.
- `JEU_DONNEES` and `LIGNE_JEU_DONNEES` allow versioned train, validation, and test sets.

## Certification ERD (logical overview)

```mermaid
erDiagram
    data_source_system {
        uuid id PK
        text name UK
        text source_type
        text owner_name
        text legal_basis
        boolean contains_personal_data
        integer retention_days
        boolean is_active
        timestamptz created_at
        timestamptz updated_at
    }

    data_ingestion_run {
        uuid id PK
        uuid source_system_id FK
        timestamptz started_at
        timestamptz finished_at
        text status
        text trigger_mode
        integer raw_object_count
        integer raw_record_count
        text log_message
        timestamptz created_at
    }

    data_raw_object {
        uuid id PK
        uuid ingestion_run_id FK
        text external_ref
        text object_type
        text storage_uri
        text source_format
        text content_hash
        bigint size_bytes
        jsonb source_metadata
        timestamptz collected_at
        timestamptz retention_until
        timestamptz created_at
    }

    data_raw_record {
        uuid id PK
        uuid raw_object_id FK
        text record_key
        text raw_content
        text detected_language
        boolean is_usable
        text rejection_reason
        timestamptz extracted_at
        timestamptz created_at
    }

    data_processing_run {
        uuid id PK
        text pipeline_version
        timestamptz started_at
        timestamptz finished_at
        text status
        integer normalized_count
        integer rejected_count
        text report_uri
        timestamptz created_at
    }

    data_normalized_message {
        uuid id PK
        uuid raw_record_id FK
        uuid processing_run_id FK
        text normalized_text
        text text_sha256 UK
        text language
        text current_label
        real quality_score
        boolean contains_pii
        text redaction_status
        integer text_length
        timestamptz normalized_at
        timestamptz created_at
        timestamptz updated_at
    }

    data_annotation {
        uuid id PK
        uuid normalized_message_id FK
        text label
        text label_source
        real confidence
        text comment
        boolean is_validated
        timestamptz annotated_at
        timestamptz created_at
    }

    data_dataset {
        uuid id PK
        text name
        text version_tag UK
        text target_usage
        text status
        timestamptz frozen_at
        integer item_count
        timestamptz created_at
    }

    data_dataset_item {
        uuid id PK
        uuid dataset_id FK
        uuid normalized_message_id FK
        text split_name
        real sample_weight
        integer row_order
        timestamptz created_at
    }

    data_source_system ||--o{ data_ingestion_run : produces
    data_ingestion_run ||--o{ data_raw_object : collects
    data_raw_object ||--o{ data_raw_record : contains
    data_processing_run ||--o{ data_normalized_message : creates
    data_raw_record ||--o| data_normalized_message : becomes
    data_normalized_message ||--o{ data_annotation : receives
    data_dataset ||--o{ data_dataset_item : contains
    data_normalized_message ||--o{ data_dataset_item : joins
```

## MLD (logical relational model)

### Logical table list

| Table | Role | Key relationships |
|-------|------|-------------------|
| `data_source_system` | source catalog and governance registry | parent of ingestion runs |
| `data_ingestion_run` | execution trace for one collection run | child of source system |
| `data_raw_object` | collected file, payload, or snapshot | child of ingestion run |
| `data_raw_record` | extracted row, message, page, or unit | child of raw object |
| `data_processing_run` | execution trace for normalization pipeline | linked to normalized messages |
| `data_normalized_message` | curated NLP-ready message | child of raw record and processing run |
| `data_annotation` | labels and validation metadata | child of normalized message |
| `data_dataset` | frozen dataset version | parent of dataset items |
| `data_dataset_item` | membership of a message in a dataset split | child of dataset and normalized message |

### Logical constraints

- one source system can generate many ingestion runs
- one ingestion run can generate many raw objects
- one raw object can contain many raw records
- one raw record can yield zero or one normalized message
- one normalized message can receive many annotations
- one dataset contains many dataset items
- one normalized message can belong to several datasets over time

### Logical enums

Recommended controlled vocabularies:

- `source_type`: `api`, `file`, `scraping`, `sql`, `bigdata`, `manual`
- `status` for runs: `pending`, `running`, `completed`, `failed`, `partial`
- `object_type`: `file`, `api_payload`, `html_page`, `sql_export`, `bigdata_extract`
- `current_label` and `label`: `phishing`, `spam`, `legitimate`, `unknown`
- `split_name`: `train`, `val`, `test`, `holdout`
- `redaction_status`: `not_required`, `redacted`, `review_needed`

## MPD (physical model for PostgreSQL)

### Target SGBD

- Production target: PostgreSQL
- Local development and CI: SQLite via dialect abstraction
- Migration tool: Alembic

### Physical table definitions

#### `data_source_system`

| Column | Type | Constraints |
|--------|------|------------|
| id | uuid | PK, DEFAULT gen_random_uuid() |
| name | text | NOT NULL, UNIQUE |
| source_type | text | NOT NULL, CHECK(source_type IN ('api','file','scraping','sql','bigdata','manual')) |
| description | text | |
| owner_name | text | |
| legal_basis | text | |
| contains_personal_data | boolean | NOT NULL, DEFAULT false |
| retention_days | integer | |
| is_active | boolean | NOT NULL, DEFAULT true |
| created_at | timestamptz | NOT NULL, DEFAULT now() |
| updated_at | timestamptz | |

#### `data_ingestion_run`

| Column | Type | Constraints |
|--------|------|------------|
| id | uuid | PK |
| source_system_id | uuid | NOT NULL, FK -> data_source_system(id) ON DELETE RESTRICT |
| started_at | timestamptz | NOT NULL |
| finished_at | timestamptz | |
| status | text | NOT NULL, CHECK(status IN ('pending','running','completed','failed','partial')) |
| trigger_mode | text | NOT NULL |
| raw_object_count | integer | NOT NULL, DEFAULT 0 |
| raw_record_count | integer | NOT NULL, DEFAULT 0 |
| log_message | text | |
| created_at | timestamptz | NOT NULL, DEFAULT now() |

Index strategy:

- `idx_ingestion_source_started` on `(source_system_id, started_at DESC)`

#### `data_raw_object`

| Column | Type | Constraints |
|--------|------|------------|
| id | uuid | PK |
| ingestion_run_id | uuid | NOT NULL, FK -> data_ingestion_run(id) ON DELETE CASCADE |
| external_ref | text | |
| object_type | text | NOT NULL, CHECK(object_type IN ('file','api_payload','html_page','sql_export','bigdata_extract')) |
| storage_uri | text | |
| source_format | text | |
| content_hash | text | NOT NULL |
| size_bytes | bigint | |
| source_metadata | jsonb | NOT NULL, DEFAULT '{}' |
| collected_at | timestamptz | NOT NULL |
| retention_until | timestamptz | |
| created_at | timestamptz | NOT NULL, DEFAULT now() |

Index strategy:

- `idx_raw_object_ingestion` on `(ingestion_run_id)`
- `uq_raw_object_hash` UNIQUE `(ingestion_run_id, content_hash, external_ref)`

#### `data_raw_record`

| Column | Type | Constraints |
|--------|------|------------|
| id | uuid | PK |
| raw_object_id | uuid | NOT NULL, FK -> data_raw_object(id) ON DELETE CASCADE |
| record_key | text | NOT NULL |
| raw_content | text | NOT NULL |
| detected_language | text | |
| is_usable | boolean | NOT NULL, DEFAULT true |
| rejection_reason | text | |
| extracted_at | timestamptz | NOT NULL |
| created_at | timestamptz | NOT NULL, DEFAULT now() |

Index strategy:

- `uq_raw_record_key` UNIQUE `(raw_object_id, record_key)`

#### `data_processing_run`

| Column | Type | Constraints |
|--------|------|------------|
| id | uuid | PK |
| pipeline_version | text | NOT NULL |
| started_at | timestamptz | NOT NULL |
| finished_at | timestamptz | |
| status | text | NOT NULL, CHECK(status IN ('pending','running','completed','failed','partial')) |
| normalized_count | integer | NOT NULL, DEFAULT 0 |
| rejected_count | integer | NOT NULL, DEFAULT 0 |
| report_uri | text | |
| created_at | timestamptz | NOT NULL, DEFAULT now() |

#### `data_normalized_message`

| Column | Type | Constraints |
|--------|------|------------|
| id | uuid | PK |
| raw_record_id | uuid | NOT NULL, FK -> data_raw_record(id) ON DELETE RESTRICT |
| processing_run_id | uuid | NOT NULL, FK -> data_processing_run(id) ON DELETE RESTRICT |
| normalized_text | text | NOT NULL |
| text_sha256 | text | NOT NULL, UNIQUE |
| language | text | NOT NULL |
| current_label | text | NOT NULL, CHECK(current_label IN ('phishing','spam','legitimate','unknown')) |
| quality_score | real | |
| contains_pii | boolean | NOT NULL, DEFAULT false |
| redaction_status | text | NOT NULL, DEFAULT 'not_required', CHECK(redaction_status IN ('not_required','redacted','review_needed')) |
| text_length | integer | NOT NULL |
| normalized_at | timestamptz | NOT NULL |
| created_at | timestamptz | NOT NULL, DEFAULT now() |
| updated_at | timestamptz | |

Index strategy:

- `idx_message_label_lang` on `(current_label, language)`
- `idx_message_processing_run` on `(processing_run_id)`

#### `data_annotation`

| Column | Type | Constraints |
|--------|------|------------|
| id | uuid | PK |
| normalized_message_id | uuid | NOT NULL, FK -> data_normalized_message(id) ON DELETE CASCADE |
| label | text | NOT NULL, CHECK(label IN ('phishing','spam','legitimate','unknown')) |
| label_source | text | NOT NULL |
| confidence | real | CHECK(confidence BETWEEN 0 AND 1) |
| comment | text | |
| is_validated | boolean | NOT NULL, DEFAULT false |
| annotated_at | timestamptz | NOT NULL |
| created_at | timestamptz | NOT NULL, DEFAULT now() |

Index strategy:

- `idx_annotation_message_date` on `(normalized_message_id, annotated_at DESC)`

#### `data_dataset`

| Column | Type | Constraints |
|--------|------|------------|
| id | uuid | PK |
| name | text | NOT NULL |
| version_tag | text | NOT NULL, UNIQUE |
| target_usage | text | NOT NULL |
| status | text | NOT NULL, CHECK(status IN ('draft','frozen','archived')) |
| frozen_at | timestamptz | |
| item_count | integer | NOT NULL, DEFAULT 0 |
| created_at | timestamptz | NOT NULL, DEFAULT now() |

#### `data_dataset_item`

| Column | Type | Constraints |
|--------|------|------------|
| id | uuid | PK |
| dataset_id | uuid | NOT NULL, FK -> data_dataset(id) ON DELETE CASCADE |
| normalized_message_id | uuid | NOT NULL, FK -> data_normalized_message(id) ON DELETE RESTRICT |
| split_name | text | NOT NULL, CHECK(split_name IN ('train','val','test','holdout')) |
| sample_weight | real | NOT NULL, DEFAULT 1.0 |
| row_order | integer | |
| created_at | timestamptz | NOT NULL, DEFAULT now() |

Index strategy:

- `uq_dataset_message` UNIQUE `(dataset_id, normalized_message_id)`
- `idx_dataset_split` on `(dataset_id, split_name)`

## CRUD policy for the data platform

Not every table should be equally mutable.

### Full CRUD

- `data_source_system`
- `data_annotation`
- `data_dataset`
- `data_dataset_item` while the dataset is still in `draft`

### Create and read, controlled updates only

- `data_normalized_message`
  - allowed updates: corrected label, redaction status, quality metadata

### Append-only with retention-driven deletion

- `data_ingestion_run`
- `data_raw_object`
- `data_raw_record`
- `data_processing_run`

This preserves lineage and makes the SQL platform defensible during evaluation.

## RGPD and retention rules

- raw content is retained only as long as necessary for reproducibility and audit
- normalized text must be redacted before long-term retention
- source-level legal basis and retention are tracked in `data_source_system`
- records may be deleted by retention policy from raw tables without breaking dataset history if curated text is preserved lawfully

## Secondary schema: product runtime model

The following runtime entities remain valid for the final SaaS application, but they are not the primary MCD for Bloc 1:

- `users`
- `oauth_tokens`
- `watch_state`
- `threat_log`
- `feedback`
- `model_versions`
- `sessions`

These runtime tables should be documented and implemented as a separate application-domain schema after the data platform baseline is established.
