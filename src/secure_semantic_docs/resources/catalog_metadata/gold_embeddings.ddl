-- Schema: gold
-- Table:  embeddings
-- Full identifier (Iceberg / production): <catalog>.gold.embeddings
-- Parquet path (local):                   lakehouse/gold_embeddings/
--
-- Enriched chunks with embedding vectors, ready for vector search.
-- One row per chunk, derived from silver.chunks.
-- Populated by the embedding pipeline (pipeline/gold.py).

CREATE TABLE IF NOT EXISTS gold.embeddings (
    chunk_id             STRING          NOT NULL COMMENT 'Unique chunk identifier, foreign key to silver.chunks',
    document_id          STRING          NOT NULL COMMENT 'Parent document identifier, foreign key to bronze.documents',
    embedding            ARRAY<FLOAT>    COMMENT 'Dense embedding vector produced by the embedding model',
    embedding_model      STRING          COMMENT 'Name of the SentenceTransformer model used (e.g. all-MiniLM-L6-v2)',
    embedding_created_at STRING          COMMENT 'ISO-8601 timestamp of when the embedding was generated',
    classification       STRING          COMMENT 'Inherited security classification from silver.chunks',
    allowed_roles        ARRAY<STRING>   COMMENT 'Inherited permitted roles from silver.chunks',
    owner                STRING          COMMENT 'Inherited document owner name',
    department           STRING          COMMENT 'Inherited owning department',
    sensitivity_score    FLOAT           COMMENT 'Inherited sensitivity score from silver.chunks',
    source_path          STRING          COMMENT 'Inherited relative path to the source document',
    version              STRING          COMMENT 'Inherited document version',
    document_hash        STRING          COMMENT 'Inherited SHA-256 digest for lineage tracing'
)
COMMENT 'Gold layer: chunks with embedding vectors and full governance metadata. Source of truth for vector search.'
TBLPROPERTIES (
    'layer'                   = 'gold',
    'table'                   = 'embeddings',
    'full_name'               = 'gold.embeddings',
    'format'                  = 'parquet',
    'iceberg.format-version'  = '2',
    'write.format.default'    = 'parquet',
    'owner'                   = 'data_platform',
    'lineage.upstream'        = 'silver.chunks'
);
