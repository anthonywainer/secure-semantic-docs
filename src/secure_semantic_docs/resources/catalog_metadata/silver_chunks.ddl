-- Schema: silver
-- Table:  chunks
-- Full identifier (Iceberg / production): <catalog>.silver.chunks
-- Parquet path (local):                   lakehouse/silver_chunks/
--
-- Cleaned and chunked document text with sensitivity annotations.
-- One row per chunk, derived from bronze.documents.
-- Populated by the chunking pipeline (pipeline/silver.py).

CREATE TABLE IF NOT EXISTS silver.chunks (
    chunk_id                    STRING        NOT NULL COMMENT 'Unique chunk identifier: <document_id>-<chunk_index>',
    document_id                 STRING        NOT NULL COMMENT 'Parent document identifier, foreign key to bronze.documents',
    chunk_index                 INT           NOT NULL COMMENT 'Zero-based position of this chunk within the document',
    chunk_text                  STRING        COMMENT 'Cleaned and normalised text content of this chunk',
    classification              STRING        COMMENT 'Inherited security classification from the parent document',
    allowed_roles               ARRAY<STRING> COMMENT 'Inherited permitted roles from the parent document',
    owner                       STRING        COMMENT 'Inherited document owner name',
    department                  STRING        COMMENT 'Inherited owning department',
    version                     STRING        COMMENT 'Inherited document version',
    source_path                 STRING        COMMENT 'Inherited relative path to the source document',
    document_hash               STRING        COMMENT 'Inherited SHA-256 digest for lineage tracing',
    sensitivity_score           FLOAT         COMMENT 'Normalised sensitivity score in [0.0, 1.0]; higher means more sensitive',
    detected_sensitive_types    ARRAY<STRING> COMMENT 'List of detected sensitive pattern categories (e.g. email, token, payroll)',
    requires_encryption         BOOLEAN       COMMENT 'True when this chunk should be encrypted before storage',
    requires_restricted_access  BOOLEAN       COMMENT 'True when this chunk requires restricted role access'
)
COMMENT 'Silver layer: chunked and sensitivity-annotated text derived from bronze.documents. No embeddings.'
TBLPROPERTIES (
    'layer'                   = 'silver',
    'table'                   = 'chunks',
    'full_name'               = 'silver.chunks',
    'format'                  = 'parquet',
    'iceberg.format-version'  = '2',
    'write.format.default'    = 'parquet',
    'owner'                   = 'data_platform',
    'lineage.upstream'        = 'bronze.documents',
    'lineage.downstream'      = 'gold.embeddings'
);
