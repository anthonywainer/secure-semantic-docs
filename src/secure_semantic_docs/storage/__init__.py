"""Storage package for secure-semantic-docs.

Sub-modules
-----------
catalog_metadata       -- DDL-based schema loader for the bronze layer
vector_store  -- Chroma vector store wrapper (imported on demand in later layers)
"""

from secure_semantic_docs.storage.schemas import load_schema

__all__ = ["load_schema"]
