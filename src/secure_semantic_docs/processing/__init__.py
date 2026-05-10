"""Text processing helpers for chunking, normalization, and DataFrame building."""

from secure_semantic_docs.processing.chunking import (
    ChunkRecord,
    EnrichedChunkRow,
    chunk_document,
    chunk_text,
    chunk_word_spans,
    clean_text,
    normalise_whitespace,
    remove_control_characters
)
from secure_semantic_docs.processing.metadata_builder import conform_document_metadata

__all__ = [
    "ChunkRecord",
    "EnrichedChunkRow",
    "conform_document_metadata",
    "chunk_document",
    "chunk_text",
    "chunk_word_spans",
    "clean_text",
    "normalise_whitespace",
    "remove_control_characters"
]
