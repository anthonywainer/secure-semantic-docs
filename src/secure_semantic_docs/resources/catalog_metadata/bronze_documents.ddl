-- Schema: bronze
-- Table:  documents
-- Full identifier (Iceberg / production): <catalog>.bronze.documents
-- Parquet path (local):                   lakehouse/bronze_documents/
--
-- Raw ingested documents. One row per source document with full metadata.
-- Populated by the ingestion pipeline (pipeline/bronze.py).
-- No transformations applied beyond metadata attachment.

CREATE TABLE IF NOT EXISTS bronze.documents (
    document_id             STRING        NOT NULL COMMENT 'Unique document identifier (e.g. DOC-001)',
    title                   STRING        COMMENT 'Document title from metadata',
    source_path             STRING        COMMENT 'Relative path to the raw document file',
    raw_text                STRING        COMMENT 'Full extracted text content of the document',
    classification          STRING        COMMENT 'Security classification: public | internal | confidential | restricted',
    owner                   STRING        COMMENT 'Full name of the document owner',
    department              STRING        COMMENT 'Owning department name',
    allowed_roles           ARRAY<STRING> COMMENT 'Roles permitted to access this document',
    version                 STRING        COMMENT 'Document version string (e.g. 1.3)',
    created_at              STRING        COMMENT 'ISO-8601 timestamp of document creation',
    contains_sensitive_info BOOLEAN       COMMENT 'True when the document contains known sensitive patterns',
    document_hash           STRING        COMMENT 'SHA-256 hex digest of raw_text for integrity verification',
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
