"""Chroma vector candidate index integration."""

from secure_semantic_docs.vector_store.chroma_client import (
    ChromaConfig,
    build_safe_metadata,
    connect_chroma,
    query_candidates,
    upsert_candidates
)

__all__ = [
    'ChromaConfig',
    'build_safe_metadata',
    'connect_chroma',
    'query_candidates',
    'upsert_candidates'
]
