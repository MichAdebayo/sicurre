-- Sicurre current PostgreSQL schema reference.
--
-- This file mirrors the SQLAlchemy ORM baseline used by Alembic revision
-- 20260708_0001. The data-platform database is still pre-production, so the
-- retired exploratory migration chain has been replaced by this one-pass
-- physical baseline. Local development and the Streamlit POC use the same
-- logical schema on SQLite.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE data_source_system (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,
    source_type text NOT NULL CHECK (source_type IN ('api', 'file', 'scraping', 'sql', 'bigdata', 'manual')),
    description text,
    owner_name text,
    legal_basis text,
    contains_personal_data boolean NOT NULL DEFAULT false,
    retention_days integer,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz
);

CREATE TABLE data_ingestion_run (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system_id uuid NOT NULL REFERENCES data_source_system(id) ON DELETE RESTRICT,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    status text NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'partial')),
    trigger_mode text NOT NULL,
    raw_object_count integer NOT NULL DEFAULT 0,
    raw_record_count integer NOT NULL DEFAULT 0,
    log_message text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_ingestion_source_started ON data_ingestion_run (source_system_id, started_at);

CREATE TABLE data_raw_object (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ingestion_run_id uuid NOT NULL REFERENCES data_ingestion_run(id) ON DELETE CASCADE,
    external_ref text,
    object_type text NOT NULL CHECK (object_type IN ('file', 'api_payload', 'html_page', 'pdf_document', 'sql_export', 'bigdata_extract')),
    storage_uri text,
    source_format text,
    content_hash text NOT NULL,
    size_bytes bigint,
    source_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    collected_at timestamptz NOT NULL,
    retention_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_raw_object_hash UNIQUE (content_hash, external_ref)
);

CREATE INDEX idx_raw_object_ingestion ON data_raw_object (ingestion_run_id);

CREATE TABLE data_generation_run (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    generator_name text NOT NULL,
    source_name text NOT NULL,
    parent_source text,
    reference_selection_mode text,
    input_artifact_uri text,
    generated_artifact_uri text,
    comparison_artifact_uri text,
    monitor_artifact_uri text,
    status text NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'partial')),
    total_draft_count integer NOT NULL DEFAULT 0,
    usable_draft_count integer NOT NULL DEFAULT 0,
    needs_prompt_tuning_count integer NOT NULL DEFAULT 0,
    dropped_draft_count integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz
);

CREATE INDEX idx_generation_run_source_created ON data_generation_run (source_name, created_at);

CREATE TABLE data_generation_sample (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    generation_run_id uuid NOT NULL REFERENCES data_generation_run(id) ON DELETE CASCADE,
    draft_id text NOT NULL,
    scenario_id text,
    variant_index integer NOT NULL DEFAULT 0,
    source_name text NOT NULL,
    parent_source text,
    target_label text NOT NULL CHECK (target_label IN ('phishing', 'spam', 'legitimate', 'unknown')),
    primary_theme text,
    review_state text NOT NULL CHECK (review_state IN ('usable', 'needs_prompt_tuning', 'drop')),
    review_notes jsonb NOT NULL DEFAULT '[]'::jsonb,
    text_sha256 text,
    nearest_reference_raw_record_id uuid,
    nearest_similarity real,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_generation_sample_run_draft_variant UNIQUE (generation_run_id, draft_id, variant_index)
);

CREATE INDEX idx_generation_sample_run_review ON data_generation_sample (generation_run_id, review_state);

CREATE TABLE data_raw_record (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_object_id uuid NOT NULL REFERENCES data_raw_object(id) ON DELETE CASCADE,
    source_system_id uuid REFERENCES data_source_system(id) ON DELETE RESTRICT,
    generation_sample_id uuid REFERENCES data_generation_sample(id) ON DELETE RESTRICT,
    record_key text NOT NULL,
    raw_content text NOT NULL,
    detected_language text,
    is_usable boolean NOT NULL DEFAULT true,
    rejection_reason text,
    extracted_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_raw_record_key UNIQUE (raw_object_id, record_key)
);

CREATE TABLE data_processing_run (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_version text NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    status text NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'partial')),
    normalized_count integer NOT NULL DEFAULT 0,
    rejected_count integer NOT NULL DEFAULT 0,
    report_uri text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE data_normalized_message (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_record_id uuid NOT NULL REFERENCES data_raw_record(id) ON DELETE RESTRICT,
    processing_run_id uuid NOT NULL REFERENCES data_processing_run(id) ON DELETE RESTRICT,
    normalized_text text NOT NULL,
    text_sha256 text NOT NULL UNIQUE,
    language text NOT NULL,
    current_label text NOT NULL CHECK (current_label IN ('phishing', 'spam', 'legitimate', 'unknown')),
    quality_score real,
    contains_pii boolean NOT NULL DEFAULT false,
    redaction_status text NOT NULL DEFAULT 'not_required' CHECK (redaction_status IN ('not_required', 'redacted', 'review_needed')),
    text_length integer NOT NULL,
    normalized_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz
);

CREATE INDEX idx_message_label_lang ON data_normalized_message (current_label, language);
CREATE INDEX idx_message_processing_run ON data_normalized_message (processing_run_id);

CREATE TABLE data_annotation (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    normalized_message_id uuid NOT NULL REFERENCES data_normalized_message(id) ON DELETE CASCADE,
    label text NOT NULL CHECK (label IN ('phishing', 'spam', 'legitimate', 'unknown')),
    label_source text NOT NULL,
    confidence real CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    comment text,
    is_validated boolean NOT NULL DEFAULT false,
    annotated_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_annotation_message_date ON data_annotation (normalized_message_id, annotated_at);

CREATE TABLE data_dataset (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    version_tag text NOT NULL UNIQUE,
    target_usage text NOT NULL,
    status text NOT NULL CHECK (status IN ('draft', 'frozen', 'archived')),
    frozen_at timestamptz,
    item_count integer NOT NULL DEFAULT 0,
    kaggle_version_id integer,
    published_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz
);

CREATE TABLE data_dataset_item (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id uuid NOT NULL REFERENCES data_dataset(id) ON DELETE CASCADE,
    normalized_message_id uuid NOT NULL REFERENCES data_normalized_message(id) ON DELETE RESTRICT,
    split_name text NOT NULL CHECK (split_name IN ('train', 'val', 'test', 'holdout')),
    sample_weight real NOT NULL DEFAULT 1.0,
    row_order integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_dataset_message UNIQUE (dataset_id, normalized_message_id)
);

CREATE INDEX idx_dataset_split ON data_dataset_item (dataset_id, split_name);

CREATE TABLE data_generation_sample_source_link (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    generation_sample_id uuid NOT NULL REFERENCES data_generation_sample(id) ON DELETE CASCADE,
    raw_record_id uuid NOT NULL REFERENCES data_raw_record(id) ON DELETE RESTRICT,
    link_role text NOT NULL CHECK (link_role IN ('generation_seed', 'sample_input', 'nearest_reference')),
    link_order integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_generation_sample_source_link_sample_record_role UNIQUE (generation_sample_id, raw_record_id, link_role)
);

CREATE INDEX idx_generation_sample_source_link_sample_order
    ON data_generation_sample_source_link (generation_sample_id, link_order);
CREATE INDEX idx_generation_sample_source_link_raw_record
    ON data_generation_sample_source_link (raw_record_id);

CREATE TABLE pipeline_state (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_name text NOT NULL UNIQUE,
    state_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE poc_user (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL UNIQUE,
    display_name text NOT NULL,
    password_hash text NOT NULL,
    role text NOT NULL DEFAULT 'viewer',
    created_at timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz
);
