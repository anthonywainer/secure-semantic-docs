-- Schema: gold
-- Table:  embed_cache
-- Parquet path (local):                   runtime/lakehouse/embed_cache/
--
-- Encrypted embedding cache keyed by (document_hash, chunk_id).
-- Prevents re-embedding unchanged chunks across pipeline runs.
-- Internal to the gold ingestion pipeline; not a serving layer.
-- Cache hits are decrypted, re-encrypted with the current key, and written
-- to gold_embeddings. Cache misses trigger a fresh model.encode() call.

CREATE TABLE IF NOT EXISTS gold.embed_cache (
    chunk_id             STRING        NOT NULL COMMENT 'Foreign key to silver.chunks',
    document_hash        STRING        NOT NULL COMMENT 'SHA-256 digest of the source document at embedding time; invalidates entry when doc changes',
    chunk_span           STRUCT<start: INT, end: INT> COMMENT 'Word index span used to reconstruct the original text',
    embedding_ciphertext BINARY        COMMENT 'XSalsa20-Poly1305 authenticated ciphertext of the serialised float32 vector',
    embedding_nonce      BINARY        COMMENT '24-byte random nonce used for this encryption',
    embedding_algorithm  STRING        COMMENT 'Algorithm identifier (XSalsa20-Poly1305)',
    embedding_dim        INT           COMMENT 'Number of dimensions in the original embedding vector',
    key_id               STRING        COMMENT 'Identifier of the encryption key used',
    model                STRING        COMMENT 'HuggingFace model identifier',
    created_at           STRING        COMMENT 'ISO-8601 timestamp of embedding generation'
)
COMMENT 'Gold embed cache: encrypted chunk embeddings keyed by document_hash + chunk_id. Internal dedup table; not a serving layer.'
TBLPROPERTIES (
    'layer'                     = 'gold',
    'table'                     = 'embed_cache',
    'full_name'                 = 'gold.embed_cache',
    'format'                    = 'parquet',
    'iceberg.format-version'    = '2',
    'write.format.default'      = 'parquet',
    'owner'                     = 'data_platform',
    'lineage.upstream'          = 'silver.chunks',
    'lineage.downstream'        = 'gold.embeddings',
    'encryption.algorithm'      = 'XSalsa20-Poly1305'
);
