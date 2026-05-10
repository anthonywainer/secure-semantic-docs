"""Build encrypted embedding rows from chunk rows."""

from __future__ import annotations

import logging

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col, isnotnull, lit
from pyspark.sql.types import StructType

from secure_semantic_docs.core import BaseSettings
from secure_semantic_docs.embeddings.cache_rows import build_cached_embeddings
from secure_semantic_docs.embeddings.encoder import encode_missing_embeddings
from secure_semantic_docs.embeddings.vector_cache import (
    filter_reusable_cache,
    load_cache,
    split_hits_and_misses,
    write_cache
)
from secure_semantic_docs.loader import load_config
from secure_semantic_docs.models import Config
from secure_semantic_docs.models.embedding_model import resolve_embedding_settings
from secure_semantic_docs.storage.schemas import load_schema

logger = logging.getLogger(BaseSettings.APP_NAME)


def generate_embeddings(
        spark: SparkSession,
        chunks_df: DataFrame,
        config: Config | None = None
) -> DataFrame:
    """Generate encrypted embedding vectors for chunk rows.

    Parameters
    ----------
    spark:
        Active :class:`~pyspark.sql.SparkSession`.
    chunks_df:
        DataFrame with at least ``chunk_id``, ``document_id``, and
        ``chunk_span`` columns.
    config:
        Optional configuration. Loaded from YAML if *None*.

    Returns
    -------
    DataFrame
        DataFrame conforming to the configured embedding schema.
    """
    effective_config = config or load_config()
    embedding_settings = resolve_embedding_settings(spark, effective_config)
    embedding_schema: StructType = load_schema('gold_embeddings')
    embeddable_chunks_df = chunks_df.filter(isnotnull(col('chunk_span')))

    reusable_cache_df = filter_reusable_cache(
        load_cache(spark, effective_config),
        model_name=embedding_settings.model_name,
        embedding_dim=embedding_settings.embedding_dim,
        key_id=embedding_settings.key_id
    )
    cache_hits_df, misses_df = split_hits_and_misses(
        embeddable_chunks_df,
        reusable_cache_df
    )

    logger.info(
        'Generating embeddings -- model=%s device=%s batch_size=%d partitions=%d local=%s',
        embedding_settings.model_name,
        embedding_settings.device,
        embedding_settings.batch_size,
        embedding_settings.num_partitions,
        embedding_settings.is_local_mode
    )

    encoded_rdd = encode_missing_embeddings(misses_df, embedding_settings)
    fresh_embeddings_df = spark.createDataFrame(encoded_rdd, schema=embedding_schema).persist()

    write_cache(
        spark,
        fresh_embeddings_df.withColumn("model", lit(embedding_settings.model_name)),
        effective_config
    )
    cached_embeddings_df = build_cached_embeddings(
        cache_hits_df,
        embedding_settings.key_id,
        embedding_settings.created_at,
        embedding_schema
    )
    return fresh_embeddings_df.union(cached_embeddings_df)
