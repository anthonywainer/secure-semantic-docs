"""Spark DataFrame builder for enriched document chunks.

Transforms a metadata DataFrame into a chunk DataFrame with sensitivity
metadata attached. File content is read from the filesystem at partition time
using the ``source_path`` reference in each row.

The public entry points are :func:`create_enriched_chunks` and
:func:`create_chunk_workset`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from pyspark.sql import DataFrame, Row, SparkSession
from pyspark.sql.types import StringType, StructField, StructType

from secure_semantic_docs.core import BaseSettings
from secure_semantic_docs.models import Config
from secure_semantic_docs.processing.chunking import (
    EnrichedChunkRow,
    chunk_document
)
from secure_semantic_docs.processing.document_reader import (
    read_document_text as _read_document_text
)
from secure_semantic_docs.security.sensitive_detector import enrich_chunks_with_sensitivity
from secure_semantic_docs.storage.schemas import load_schema

logger = logging.getLogger(BaseSettings.APP_NAME)


def _enrich_partition(
        document_rows: Iterable[Row],
        chunk_size: int,
        chunk_overlap: int,
        raw_docs_dir: str
) -> Iterable[EnrichedChunkRow]:
    """Yield one :data:`EnrichedChunkRow` per chunk for every document row."""
    for document_row in document_rows:
        payload = dict(document_row.asDict())
        payload["raw_text"] = _read_document_text(
            str(payload.get("source_path", "")), raw_docs_dir
        )
        raw_chunks = chunk_document(payload, chunk_size, chunk_overlap)
        for enriched in enrich_chunks_with_sensitivity(raw_chunks):
            start, end = _chunk_span(enriched["chunk_span"])
            yield (
                str(enriched["chunk_id"]),
                str(enriched["document_id"]),
                int(enriched["chunk_index"]),  # type: ignore[arg-type]
                Row(start=start, end=end),
                str(enriched["classification"]),
                list(enriched["allowed_roles"]),  # type: ignore[arg-type]
                str(enriched["owner"]),
                str(enriched["department"]),
                str(enriched["version"]),
                str(enriched["source_path"]),
                str(enriched["document_hash"]),
                float(enriched["sensitivity_score"]),  # type: ignore[arg-type]
                list(enriched["detected_sensitive_types"]),  # type: ignore[arg-type]
                bool(enriched["requires_encryption"]),
                bool(enriched["requires_restricted_access"]),
                str(enriched["chunk_text"])
            )


def create_chunk_workset(
        spark: SparkSession,
        documents_df: DataFrame,
        config: Config | None = None
) -> DataFrame:
    """Return transient enriched chunks including ``chunk_text``.

    Reads each document's text from disk at partition time, splits it into
    chunks, and attaches sensitivity metadata to each chunk. The returned
    DataFrame is an execution workset only; callers must not persist it as a
    lakehouse table because it includes plaintext ``chunk_text``.

    Parameters
    ----------
    spark:
        Active SparkSession.
    documents_df:
        Metadata DataFrame with at least ``document_id`` and
        ``source_path`` columns.
    config:
        Pipeline configuration. A default :class:`~secure_semantic_docs.models.Config`
        is constructed when *None*.

    Returns
    -------
    DataFrame
        Chunk DataFrame with the silver columns plus transient ``chunk_text``.
    """
    effective_config = config or Config()
    chunk_size = effective_config.chunking.chunk_size
    chunk_overlap = effective_config.chunking.chunk_overlap
    raw_docs_reader = effective_config.readers.entries.get("raw_documents")
    raw_docs_dir: str = (
        str(raw_docs_reader.options["path"])
        if raw_docs_reader is not None
        else str(effective_config.raw_documents_dir)
    )

    chunks_rdd = documents_df.rdd.mapPartitions(
        lambda rows: _enrich_partition(rows, chunk_size, chunk_overlap, raw_docs_dir)
    )
    return spark.createDataFrame(chunks_rdd, schema=_workset_schema())


def create_enriched_chunks(
        spark: SparkSession,
        documents_df: DataFrame,
        config: Config | None = None
) -> DataFrame:
    """Return persisted chunk metadata built from *documents_df*."""
    return select_persisted_chunk_columns(
        create_chunk_workset(spark, documents_df, config)
    )


def select_persisted_chunk_columns(chunks_df: DataFrame) -> DataFrame:
    """Drop transient fields and return a DataFrame matching ``silver_chunks``."""
    silver_schema = load_schema("silver_chunks")
    return chunks_df.select(*[field.name for field in _schema_fields(silver_schema)])


def _workset_schema() -> StructType:
    return load_schema("silver_chunks").add("chunk_text", StringType(), True)


def _schema_fields(schema: StructType) -> list[StructField]:
    return list(schema.fields or [])


def _chunk_span(span: object) -> tuple[int, int]:
    if not isinstance(span, tuple) or len(span) != 2:
        raise ValueError("chunk_span must be a two-item tuple.")
    start, end = span
    return int(start), int(end)
