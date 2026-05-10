"""Metadata catalogue transform.

Accepts a raw metadata DataFrame, attaches an ingestion timestamp, and casts
all fields to the documents DDL schema.  Loading is the caller's responsibility.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pyspark.sql import DataFrame
from pyspark.sql.functions import col, lit
from pyspark.sql.types import StructField

from secure_semantic_docs.storage import load_schema

_METADATA_COLUMNS = [
    "document_id",
    "title",
    "source_path",
    "classification",
    "owner",
    "department",
    "allowed_roles",
    "version",
    "created_at",
    "contains_sensitive_info",
    "document_hash"
]


def conform_document_metadata(raw_df: DataFrame) -> DataFrame:
    """Return a schema-conformant metadata DataFrame.

    Selects the expected catalogue columns, attaches an ingestion timestamp,
    and casts each field to the type defined in ``bronze_documents.ddl``.

    Parameters
    ----------
    raw_df:
        Raw metadata DataFrame as loaded by the caller.

    Returns
    -------
    DataFrame
        Metadata DataFrame conforming to ``bronze_documents.ddl``.
    """
    metadata_df = raw_df.select(*[col(c) for c in _METADATA_COLUMNS])

    ingestion_ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    document_schema = load_schema("bronze_documents")

    return metadata_df.select(
        *[_cast_field(f, ingestion_ts) for f in document_schema]
    )


def _cast_field(f: StructField, ingestion_ts: str):
    if f.name == "ingestion_timestamp":
        return lit(ingestion_ts).cast(f.dataType).alias("ingestion_timestamp")
    return col(f.name).cast(f.dataType)
