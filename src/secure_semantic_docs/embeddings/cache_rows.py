"""Build encrypted embedding rows from reusable cache hits."""

from __future__ import annotations

import uuid

from pyspark.sql import DataFrame
from pyspark.sql.column import Column
from pyspark.sql.functions import col, lit
from pyspark.sql.types import StructField, StructType


def build_cached_embeddings(
        hits_df: DataFrame,
        current_key_id: str,
        created_at: str,
        embedding_schema: StructType
) -> DataFrame:
    """Convert cache hits encrypted with the active key into embedding rows."""
    if "key_id" not in {field.name for field in hits_df.schema}:
        empty_rdd = hits_df.sparkSession.sparkContext.emptyRDD()
        return hits_df.sparkSession.createDataFrame(empty_rdd, embedding_schema)

    same_key_hits = hits_df.filter(col("key_id") == current_key_id)
    available_columns = {field.name for field in same_key_hits.schema}

    select_exprs = [
        _output_column_expr(field.name, available_columns, created_at)
        for field in _schema_fields(embedding_schema)
    ]
    return same_key_hits.select(*select_exprs)


def _schema_fields(schema: StructType) -> list[StructField]:
    return list(schema.fields or [])


def _output_column_expr(
        output_column: str,
        available_columns: set[str],
        created_at: str
) -> Column:
    if output_column == "embedding_id":
        return lit(str(uuid.uuid4())).alias("embedding_id")
    if output_column == "created_at":
        return lit(created_at).alias("created_at")
    if output_column == "embedding_model" and "model" in available_columns:
        return col("model").alias("embedding_model")
    if output_column in available_columns:
        return col(output_column)
    return lit(None).alias(output_column)
