"""Embedding generation package for encrypted embedding rows.

Public API
----------
generate_embeddings(spark, chunks_df, config) -> DataFrame
    Transform chunk rows into an encrypted embedding DataFrame by encoding
    each chunk and encrypting the resulting vectors.

Internal modules (not part of the public API)
----------------------------------------------
core.py
    Driver-side Spark DataFrame builder for encrypted embeddings.
cache_rows.py
    Convert reusable cache rows into embedding output rows.
encoder.py
    Driver-side Spark repartitioning and partition encoder dispatch.
row_encoder.py
    Worker-side partition encoding and encryption logic.
model_loader.py
    Per-worker-process model cache and device resolution.
worker_env.py
    Process-level environment variable setup (must run before any tokenizer
    import inside executor processes).

See also
--------
:mod:`secure_semantic_docs.core.spark_partitions`
    Partition-count selection for CPU-bound Spark jobs (shared utility).
"""

from secure_semantic_docs.embeddings.core import generate_embeddings

__all__ = ["generate_embeddings"]
