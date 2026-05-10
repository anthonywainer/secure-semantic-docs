"""Shared type contracts for embedding generation."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

type EmbeddingMatrix = Iterable[Any]

type EmbeddingRow = tuple[
    str,
    str,
    str,
    bytes,
    bytes,
    str,
    int,
    str,
    str,
    str,
    str | None,
    list | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str
]


class EmbeddingModel(Protocol):
    """Minimal SentenceTransformer interface used by partition encoding."""

    def encode(
            self,
            texts: list[str],
            *,
            normalize_embeddings: bool,
            show_progress_bar: bool,
            batch_size: int
    ) -> EmbeddingMatrix:
        """Return an embedding matrix for *texts*."""
        ...  # pragma: no cover
