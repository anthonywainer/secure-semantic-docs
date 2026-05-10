"""Reconstruct chunk text from transient fields or source document spans."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from secure_semantic_docs.processing.document_reader import read_document_words


def chunk_texts(chunk_rows: list[dict[str, Any]], raw_docs_dir: str) -> list[str]:
    """Return text for chunk rows using transient text or source span lookup."""
    words_cache: dict[str, list[str]] = {}

    def get_words(source_path: str) -> list[str]:
        if source_path not in words_cache:
            words_cache[source_path] = read_document_words(source_path, raw_docs_dir)
        return words_cache[source_path]

    return [_chunk_text(chunk_fields, get_words) for chunk_fields in chunk_rows]


def _chunk_text(
        chunk_fields: Mapping[str, Any],
        get_words: Callable[[str], list[str]]
) -> str:
    chunk_text = chunk_fields.get('chunk_text')
    if isinstance(chunk_text, str) and chunk_text:
        return chunk_text

    start, end = _span_bounds(chunk_fields.get('chunk_span'))
    words = get_words(str(chunk_fields.get('source_path', '') or ''))
    return ' '.join(words[start:end])


def _span_bounds(span: object) -> tuple[int, int]:
    if span is None:
        return 0, 0
    start = getattr(span, "start", None)
    end = getattr(span, "end", None)
    return int(start or 0), int(end or 0)
