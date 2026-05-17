-- Schema: gold
-- Table:  embeddings
-- Full identifier (Iceberg / production): <catalog>.gold.embeddings
-- Parquet path (local):                   runtime/lakehouse/gold_embeddings/
--
-- Encrypted embedding records, ready for authorised in-memory similarity search.
-- Plaintext vectors are never stored here.  Each row holds an authenticated
-- ciphertext + nonce pair that can only be decrypted with the key identified by
-- key_id.  Access control (allowed_roles / classification) is enforced as a
-- metadata filter BEFORE any decryption occurs.
-- One row per chunk, derived from silver.chunks.

CREATE TABLE IF NOT EXISTS gold.embeddings (
    embedding_id         STRING          NOT NULL COMMENT 'UUID assigned per embedding at generation time',
    chunk_id             STRING          NOT NULL COMMENT 'Foreign key to silver.chunks',
    document_id          STRING          NOT NULL COMMENT 'Foreign key to bronze.documents',
    embedding_ciphertext BINARY          COMMENT 'XSalsa20-Poly1305 authenticated ciphertext of the serialised float32 vector',
    embedding_nonce      BINARY          COMMENT '24-byte random nonce used for this encryption; required for decryption',
    embedding_algorithm  STRING          COMMENT 'Algorithm identifier (XSalsa20-Poly1305)',
    embedding_dim        INT             COMMENT 'Number of dimensions in the original embedding vector',
    embedding_dtype      STRING          COMMENT 'Numpy dtype of the original vector (float32)',
    embedding_model      STRING          COMMENT 'HuggingFace model identifier (e.g. all-MiniLM-L6-v2)',
    key_id               STRING          COMMENT 'Identifier of the encryption key used; safe to store and log',
    classification       STRING          COMMENT 'Security classification inherited from silver.chunks (public / internal / confidential / restricted)',
    allowed_roles        ARRAY<STRING>   COMMENT 'Roles permitted to decrypt and use this embedding',
    owner                STRING          COMMENT 'Inherited document owner name',
    department           STRING          COMMENT 'Inherited owning department',
    source_path          STRING          COMMENT 'Inherited relative path to the source document',
    version              STRING          COMMENT 'Inherited document version',
    document_hash        STRING          COMMENT 'Inherited SHA-256 digest for lineage tracing',
    created_at           STRING          COMMENT 'ISO-8601 timestamp of embedding generation'
)
COMMENT 'Gold layer: encrypted chunk embeddings with governance metadata. Never stores plaintext vectors.'
TBLPROPERTIES (
    'layer'                   = 'gold',
    'table'                   = 'embeddings',
    'full_name'               = 'gold.embeddings',
    'format'                  = 'parquet',
    'iceberg.format-version'  = '2',
    'write.format.default'    = 'parquet',
    'owner'                   = 'data_platform',
    'lineage.upstream'        = 'silver.chunks',
    'encryption.algorithm'    = 'XSalsa20-Poly1305',
    'encryption.key_management' = 'local-dev-only'
);
