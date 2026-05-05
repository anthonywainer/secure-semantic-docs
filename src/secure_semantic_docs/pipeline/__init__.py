"""Pipeline package for secure-semantic-docs.

Sub-modules
-----------
text          -- text normalisation utilities
bronze        -- PySpark bronze ingestion layer
silver        -- text chunking for the silver layer (added in silver commit)
sensitivity   -- synthetic sensitive-information detection (added in silver commit)
gold          -- embedding generation for the gold layer (added in gold commit)

Schemas for each layer are defined as DDL files in
``resources/schemas/`` and loaded via
:func:`~secure_semantic_docs.storage.schemas.load_schema`.
"""

from secure_semantic_docs.pipeline.bronze import ingest_documents, read_bronze
from secure_semantic_docs.spark import build_spark_session

# Backward-compatible alias -- prefer build_spark_session going forward.
create_spark_session = build_spark_session

__all__ = [
    "build_spark_session",
    "create_spark_session",
    "ingest_documents",
    "read_bronze"
]
