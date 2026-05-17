"""Encrypted embedding dedup store.

Prevents re-embedding unchanged chunks across pipeline runs. The cache is
keyed by ``(chunk_id, document_hash)``. A cache hit means the document content
has not changed since the chunk was last embedded; the stored ciphertext can be
reused directly without calling the model.

Security
--------
The cache stores only encrypted vectors — never plaintext float32 arrays.
Cache hits are reused only when the stored key identifier matches the active
key; key rotation requires fresh embedding output.

Integration
-----------
The cache is internal to embedding generation and must not be queried by
downstream consumers.
"""

from __future__ import annotations

import logging

from py4j.protocol import Py4JJavaError
from pyspark.errors import AnalysisException, PySparkException
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col, isnotnull

from secure_semantic_docs.core import BaseSettings
from secure_semantic_docs.io import SparkReader, SparkWriter
from secure_semantic_docs.models import Config

logger = logging.getLogger(BaseSettings.APP_NAME)

_CACHE_KEY_COLS = ("chunk_id", "document_hash")

_CACHE_COLS = [
    "chunk_id", "document_hash", "chunk_span",
    "embedding_ciphertext", "embedding_nonce", "embedding_algorithm",
    "embedding_dim", "key_id", "model", "created_at"
]


def load_cache(spark: SparkSession, config: Config) -> DataFrame | None:
    """Return the vector cache DataFrame, or *None* if no cache exists yet.

    Parameters
    ----------
    spark:
        Active SparkSession.
    config:
        Pipeline configuration providing the ``embed_cache`` reader entry.
    """
    reader_entry = config.readers.entries.get("embed_cache")
    if reader_entry is None:
        logger.warning("No embed_cache reader configured — cache disabled.")
        return None

    try:
        logger.info("Vector cache configured.")
        return SparkReader(spark).read(**reader_entry.options)
    except (AnalysisException, Py4JJavaError, PySparkException, OSError):
        logger.info("Vector cache not found — starting cold.")
        return None


def split_hits_and_misses(
        chunks_df: DataFrame,
        cache_df: DataFrame | None
) -> tuple[DataFrame, DataFrame]:
    """Partition *chunks_df* into cache hits and misses.

    A hit is a chunk row whose ``(chunk_id, document_hash)`` exists in
    *cache_df*. Hits can skip model inference; misses must be embedded.

    Parameters
    ----------
    chunks_df:
        Chunk DataFrame with ``chunk_id`` and ``document_hash`` columns.
    cache_df:
        Vector cache DataFrame, or *None* when the cache is cold.

    Returns
    -------
    tuple[DataFrame, DataFrame]
        ``(hits, misses)`` where *hits* are chunk rows joined with their
        cached embedding rows, and *misses* are chunk rows with no cache entry.
    """
    if cache_df is None:
        empty = chunks_df.filter(col("chunk_id") == "")
        return empty, chunks_df

    cache_keys = cache_df.select(*_CACHE_KEY_COLS).dropDuplicates(list(_CACHE_KEY_COLS))
    hits_keys = chunks_df.join(cache_keys, list(_CACHE_KEY_COLS), "inner")
    misses = chunks_df.join(cache_keys, list(_CACHE_KEY_COLS), "left_anti")

    logger.info("Vector cache split planned.")

    hits_with_cache = hits_keys.join(
        cache_df.select(
            *_CACHE_KEY_COLS,
            "embedding_ciphertext",
            "embedding_nonce",
            "embedding_algorithm",
            "embedding_dim",
            "key_id",
            "model"
        ),
        list(_CACHE_KEY_COLS),
        "inner"
    )
    return hits_with_cache, misses


def filter_reusable_cache(
        cache_df: DataFrame | None,
        *,
        model_name: str,
        embedding_dim: int,
        key_id: str
) -> DataFrame | None:
    """Return cache rows compatible with the current embedding run."""
    if cache_df is None:
        return None

    available = {field.name for field in cache_df.schema}
    filters = []
    if "model" in available:
        filters.append(col("model") == model_name)
    if "embedding_dim" in available:
        filters.append(col("embedding_dim") == embedding_dim)
    if "key_id" in available:
        filters.append(col("key_id") == key_id)

    reusable_cache_df = cache_df
    for condition in filters:
        reusable_cache_df = reusable_cache_df.filter(condition)
    return reusable_cache_df


def write_cache(spark: SparkSession, new_embeddings_df: DataFrame, config: Config) -> None:
    """Append newly computed embeddings to the vector cache.

    Only rows produced from cache misses (i.e. fresh model.encode() calls)
    should be passed here. Cache hits are not re-written.

    Parameters
    ----------
    spark:
        Active SparkSession.
    new_embeddings_df:
        DataFrame of freshly computed embeddings with at least ``chunk_id``,
        ``document_hash``, ``chunk_span``, ``embedding_ciphertext``,
        ``embedding_nonce``, ``embedding_algorithm``, ``embedding_dim``,
        ``key_id``, ``model``, and ``created_at`` columns.
    config:
        Pipeline configuration providing the ``embed_cache`` writer entry.
    """
    writer_entry = config.writers.entries.get("embed_cache")
    if writer_entry is None:
        logger.warning("No embed_cache writer configured — skipping cache write.")
        return

    available = {f.name for f in new_embeddings_df.schema}
    cols_to_write = [c for c in _CACHE_COLS if c in available]

    filtered_df = (
        new_embeddings_df
        .select(*cols_to_write)
        .filter(isnotnull(col("embedding_ciphertext")))
        .dropDuplicates(list(_CACHE_KEY_COLS))
    )
    SparkWriter(spark).write(filtered_df, **writer_entry.options)
    logger.info("Vector cache updated — appended new entries.")
