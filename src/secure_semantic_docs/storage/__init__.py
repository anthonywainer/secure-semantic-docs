"""Storage package for secure-semantic-docs.

Sub-modules
-----------
schemas      -- DDL-based schema loader for the lakehouse layers
"""

from secure_semantic_docs.storage.schemas import load_schema

__all__ = ["load_schema"]
