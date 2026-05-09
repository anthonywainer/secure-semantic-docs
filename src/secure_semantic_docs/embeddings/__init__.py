"""Embedding generation package for the gold ingestion pipeline.

Public API
----------
generate_embeddings(spark, silver_df, config) -> DataFrame
    Transform a silver-layer DataFrame into a gold-layer DataFrame by adding
    dense embedding vectors to every chunk row.

Internal modules (not part of the public API)
----------------------------------------------
encoder.py
    Partition-level encode logic and Spark DataFrame builder.
model_loader.py
    Per-worker-process model cache and device resolution.
worker_env.py
    Process-level environment variable setup (must run before any tokenizer
    import inside executor processes).
"""

from secure_semantic_docs.embeddings.chunk_embedder import generate_embeddings

__all__ = ["generate_embeddings"]
