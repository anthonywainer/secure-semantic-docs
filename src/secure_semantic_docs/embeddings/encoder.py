"""Spark driver helpers for partition-level embedding encoding."""

from __future__ import annotations

from pyspark import RDD
from pyspark.sql import DataFrame
from pyspark.sql.functions import col

from secure_semantic_docs.embeddings.row_encoder import encode_and_encrypt_partition
from secure_semantic_docs.embeddings.typing import EmbeddingRow
from secure_semantic_docs.models.embedding_model import EmbeddingSettings


def encode_missing_embeddings(
        misses_df: DataFrame,
        settings: EmbeddingSettings
) -> RDD[EmbeddingRow]:
    """Encode rows that were not found in the embedding cache."""
    balanced_misses_df = misses_df.repartition(
        settings.num_partitions,
        col('source_path')
    )
    return balanced_misses_df.rdd.mapPartitions(
        lambda partition_rows: encode_and_encrypt_partition(
            partition_rows,
            settings.model_name,
            settings.device,
            settings.batch_size,
            settings.normalize,
            settings.created_at,
            settings.encryption_key,
            settings.key_id,
            settings.embedding_dim,
            'float32',
            settings.raw_docs_dir
        )
    )
