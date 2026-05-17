-- Schema: bronze
-- Table:  documents
-- Full identifier (Iceberg / production): <catalog>.bronze.documents
-- Parquet path (local):                   runtime/lakehouse/bronze_documents/
--
-- Document metadata catalogue. One row per source document.

CREATE TABLE IF NOT EXISTS bronze.documents (
    document_id             STRING        NOT NULL COMMENT 'Unique document identifier (e.g. DOC-001)',
    title                   STRING        COMMENT 'Document title from metadata',
    source_path             STRING        COMMENT 'Relative path to the raw document file; used by silver to read content',
    classification          STRING        COMMENT 'Security classification: public | internal | confidential | restricted',
    owner                   STRING        COMMENT 'Full name of the document owner',
    department              STRING        COMMENT 'Owning department name',
    allowed_roles           ARRAY<STRING> COMMENT 'Roles permitted to access this document',
    version                 STRING        COMMENT 'Document version string (e.g. 1.3)',
    created_at              STRING        COMMENT 'ISO-8601 timestamp of document creation',
    contains_sensitive_info BOOLEAN       COMMENT 'True when the document contains known sensitive patterns',
    document_hash           STRING        COMMENT 'SHA-256 hex digest of the source file for integrity verification',
    ingestion_timestamp     STRING        COMMENT 'ISO-8601 timestamp of when this record was ingested'
)
COMMENT 'Bronze layer: raw documents ingested from source. No transformations applied.'
TBLPROPERTIES (
    'layer'                   = 'bronze',
    'table'                   = 'documents',
    'full_name'               = 'bronze.documents',
    'format'                  = 'parquet',
    'iceberg.format-version'  = '2',
    'write.format.default'    = 'parquet',
    'owner'                   = 'data_platform',
    'lineage.downstream'      = 'silver.chunks'
);
