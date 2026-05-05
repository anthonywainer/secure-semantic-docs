"""Storage package for secure-semantic-docs.

Sub-modules
-----------
lakehouse     -- Parquet read/write abstraction for bronze/silver/gold layers
schemas       -- DDL-based schema loader for all lakehouse layers
vector_store  -- Chroma vector store wrapper (imported on demand in later layers)
"""

from secure_semantic_docs.storage.lakehouse import (
    read_bronze,
    read_layer,
    write_layer
)
from secure_semantic_docs.storage.schemas import load_schema

__all__ = [
    "load_schema",
    "read_bronze",
    "read_layer",
    "write_layer"
]
