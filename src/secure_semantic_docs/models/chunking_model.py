"""Chunking configuration dataclass."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkingConfig:
    """Text chunking parameters for the silver pipeline.

    Attributes
    ----------
    chunk_size:
        Maximum number of words per chunk.
    chunk_overlap:
        Number of words shared between consecutive chunks.
    default_top_k:
        Default number of results returned by semantic search queries.
    retrieval_candidate_multiplier:
        Factor applied to *default_top_k* when fetching initial candidates
        before re-ranking or filtering.
    """

    chunk_size: int = 400
    chunk_overlap: int = 80
    default_top_k: int = 5
    retrieval_candidate_multiplier: int = 4
