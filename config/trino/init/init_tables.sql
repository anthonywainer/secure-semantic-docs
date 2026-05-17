-- ============================================================
-- Trino Lakehouse Init Script
-- Creates schemas, external tables, and safe views
-- WARNING: raw schema is admin-only. safe schema is user-facing.
-- ============================================================

-- Raw schema
CREATE SCHEMA IF NOT EXISTS lakehouse.raw;

-- Safe schema (user-facing views)
CREATE SCHEMA IF NOT EXISTS lakehouse.safe;

-- -------------------------------------------------------
-- Raw: bronze_documents
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS lakehouse.raw.bronze_documents (
  document_id VARCHAR,
  title VARCHAR,
  source_path VARCHAR,
  classification VARCHAR,
  owner VARCHAR,
  department VARCHAR,
  allowed_roles ARRAY(VARCHAR),
  version VARCHAR,
  created_at VARCHAR,
  contains_sensitive_info BOOLEAN,
  document_hash VARCHAR,
  ingestion_timestamp VARCHAR
)
WITH (
  external_location = 'file:///data/lakehouse/bronze_documents',
  format = 'PARQUET'
);

-- -------------------------------------------------------
-- Raw: silver_chunks
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS lakehouse.raw.silver_chunks (
  chunk_id VARCHAR,
  document_id VARCHAR,
  chunk_index INTEGER,
  chunk_span ROW(start INTEGER, "end" INTEGER),
  classification VARCHAR,
  allowed_roles ARRAY(VARCHAR),
  owner VARCHAR,
  department VARCHAR,
  version VARCHAR,
  source_path VARCHAR,
  document_hash VARCHAR,
  sensitivity_score REAL,
  detected_sensitive_types ARRAY(VARCHAR),
  requires_encryption BOOLEAN,
  requires_restricted_access BOOLEAN
)
WITH (
  external_location = 'file:///data/lakehouse/silver_chunks',
  format = 'PARQUET'
);

-- -------------------------------------------------------
-- Raw: gold_embeddings (admin only — contains encrypted fields)
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS lakehouse.raw.gold_embeddings (
  embedding_id VARCHAR,
  chunk_id VARCHAR,
  document_id VARCHAR,
  embedding_ciphertext VARBINARY,
  embedding_nonce VARBINARY,
  embedding_algorithm VARCHAR,
  embedding_dim INTEGER,
  embedding_dtype VARCHAR,
  embedding_model VARCHAR,
  key_id VARCHAR,
  classification VARCHAR,
  allowed_roles ARRAY(VARCHAR),
  owner VARCHAR,
  department VARCHAR,
  source_path VARCHAR,
  version VARCHAR,
  document_hash VARCHAR,
  created_at VARCHAR
)
WITH (
  external_location = 'file:///data/lakehouse/gold_embeddings',
  format = 'PARQUET'
);

-- -------------------------------------------------------
-- Safe view: bronze_documents
-- -------------------------------------------------------
CREATE OR REPLACE VIEW lakehouse.safe.bronze_documents AS
SELECT
  document_id,
  title,
  source_path,
  classification,
  owner,
  department,
  allowed_roles,
  version,
  created_at,
  ingestion_timestamp
FROM lakehouse.raw.bronze_documents;

-- -------------------------------------------------------
-- Safe view: silver_chunks
-- Excludes internal policy flags (requires_encryption, etc.)
-- -------------------------------------------------------
CREATE OR REPLACE VIEW lakehouse.safe.silver_chunks AS
SELECT
  chunk_id,
  document_id,
  chunk_index,
  format('start=%s,end=%s', CAST(chunk_span.start AS VARCHAR), CAST(chunk_span."end" AS VARCHAR)) AS chunk_span,
  classification,
  allowed_roles,
  owner,
  department,
  version,
  source_path,
  document_hash,
  sensitivity_score
FROM lakehouse.raw.silver_chunks;

-- -------------------------------------------------------
-- Safe view: gold_embedding_catalog
-- CRITICAL: Never expose embedding_ciphertext, embedding_nonce, key_id
-- -------------------------------------------------------
CREATE OR REPLACE VIEW lakehouse.safe.gold_embedding_catalog AS
SELECT
  embedding_id,
  chunk_id,
  document_id,
  embedding_algorithm,
  embedding_dim,
  embedding_dtype,
  embedding_model,
  classification,
  allowed_roles,
  owner,
  department,
  source_path,
  version,
  document_hash,
  created_at
FROM lakehouse.raw.gold_embeddings;

-- -------------------------------------------------------
-- Catalog views (verbose aliases for OpenMetadata compat)
-- -------------------------------------------------------
CREATE OR REPLACE VIEW lakehouse.safe.v_bronze_documents_catalog AS
SELECT
  document_id,
  title,
  source_path,
  classification,
  owner,
  department,
  allowed_roles,
  version,
  created_at,
  ingestion_timestamp
FROM lakehouse.raw.bronze_documents;

CREATE OR REPLACE VIEW lakehouse.safe.v_silver_chunks_catalog AS
SELECT
  chunk_id,
  document_id,
  chunk_index,
  format('start=%s,end=%s', CAST(chunk_span.start AS VARCHAR), CAST(chunk_span."end" AS VARCHAR)) AS chunk_span,
  classification,
  allowed_roles,
  owner,
  department,
  version,
  source_path,
  sensitivity_score
FROM lakehouse.raw.silver_chunks;

CREATE OR REPLACE VIEW lakehouse.safe.v_gold_embedding_catalog AS
SELECT
  embedding_id,
  chunk_id,
  document_id,
  embedding_algorithm,
  embedding_dim,
  embedding_dtype,
  embedding_model,
  classification,
  allowed_roles,
  owner,
  department,
  version,
  created_at
FROM lakehouse.raw.gold_embeddings;

-- -------------------------------------------------------
-- Classification-filtered views
-- Note: Trino file-based ACL enforces schema/table access.
-- Per-row classification filtering is enforced by the
-- Python permission layer at retrieval time.
-- These views expose all rows — application layer enforces
-- per-user row-level filtering.
-- -------------------------------------------------------
CREATE OR REPLACE VIEW lakehouse.safe.v_public_chunks AS
SELECT
  chunk_id,
  document_id,
  chunk_index,
  classification,
  owner,
  department,
  version,
  source_path,
  sensitivity_score
FROM lakehouse.raw.silver_chunks
WHERE classification = 'public';

CREATE OR REPLACE VIEW lakehouse.safe.v_internal_chunks AS
SELECT
  chunk_id,
  document_id,
  chunk_index,
  classification,
  owner,
  department,
  version,
  source_path,
  sensitivity_score
FROM lakehouse.raw.silver_chunks
WHERE classification IN ('public', 'internal');

-- -------------------------------------------------------
-- Audit events view (log files not yet in Trino — placeholder)
-- When audit JSONL is exported to Parquet, point this view there.
-- -------------------------------------------------------
-- CREATE OR REPLACE VIEW lakehouse.safe.v_audit_events AS
-- SELECT * FROM lakehouse.raw.audit_events;
-- (Uncomment and create lakehouse.raw.audit_events when Parquet export is ready)

