"""Chunking and text normalization helpers."""

import re
import uuid
from collections.abc import Iterable
from typing import TypedDict

_RE_TRAILING_LINE_SPACES: re.Pattern[str] = re.compile(r"[ \t]+\n")
_RE_EXCESS_BLANK_LINES: re.Pattern[str] = re.compile(r"\n{3,}")
_RE_CONTROL_CHARS: re.Pattern[str] = re.compile(
    r"[^\x09\x0A\x0D\x20-\x7E\u00A0-\uFFFF]"
)


class ChunkRecord(TypedDict):
    """Single chunk payload prior to sensitivity enrichment."""

    chunk_id: str
    document_id: str
    chunk_index: int
    chunk_text: str
    chunk_span: tuple[int, int]
    classification: str
    allowed_roles: list[str]
    owner: str
    department: str
    version: str
    source_path: str
    document_hash: str


type EnrichedChunkRow = tuple[
    str,
    str,
    int,
    object,
    str,
    list[str],
    str,
    str,
    str,
    str,
    str,
    float,
    list[str],
    bool,
    bool,
    str
]


def chunk_text(
        document_text: str, chunk_size: int = 400, chunk_overlap: int = 80
) -> list[str]:
    """Split *document_text* into overlapping chunks by word boundaries.

    Raises :exc:`ValueError` for invalid *chunk_size* or *chunk_overlap*.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be between 0 and chunk_size - 1.")

    words = document_text.split()
    if not words:
        return []

    step = chunk_size - chunk_overlap
    return [
        " ".join(words[i:i + chunk_size])
        for i in range(0, len(words), step)
    ]


def chunk_word_spans(
        document_text: str, chunk_size: int = 400, chunk_overlap: int = 80
) -> list[tuple[int, int]]:
    """Return ``(start, end)`` word-index pairs for overlapping chunks.

    Uses the same validation and step logic as :func:`chunk_text` so that
    ``words[start:end]`` reproduces the exact text of each chunk.

    Raises :exc:`ValueError` for invalid *chunk_size* or *chunk_overlap*.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be between 0 and chunk_size - 1.")

    words = document_text.split()
    if not words:
        return []

    step = chunk_size - chunk_overlap
    return [
        (i, min(i + chunk_size, len(words)))
        for i in range(0, len(words), step)
    ]


def normalise_whitespace(raw_text: str) -> str:
    """Collapse repeated whitespace while preserving paragraph breaks."""
    return _RE_EXCESS_BLANK_LINES.sub(
        "\n\n",
        _RE_TRAILING_LINE_SPACES.sub("\n", raw_text)
    ).strip()


def remove_control_characters(raw_text: str) -> str:
    """Remove non-printable control characters except tabs and newlines."""
    return _RE_CONTROL_CHARS.sub("", raw_text)


def clean_text(raw_text: str) -> str:
    """Apply all text cleaning steps in the correct order."""
    return normalise_whitespace(remove_control_characters(raw_text))


def _normalise_allowed_roles(allowed_roles_value: object | None) -> list[str]:
    """Convert a raw allowed_roles field into a list of strings."""
    if allowed_roles_value is None:
        return []
    if isinstance(allowed_roles_value, str):
        return [allowed_roles_value]
    if isinstance(allowed_roles_value, Iterable):
        return [str(role) for role in allowed_roles_value]
    return []


def chunk_document(
        document_row: dict[str, object], chunk_size: int, chunk_overlap: int
) -> list[ChunkRecord]:
    """Produce all chunks for a single document row.

    Each record contains both ``chunk_text`` and ``chunk_span``. Only
    ``chunk_span`` is written to the silver schema; ``chunk_text`` is
    discarded after the partition completes.
    """
    cleaned_document_text = clean_text(str(document_row.get("raw_text", "") or ""))
    words = cleaned_document_text.split()
    if not words:
        return []

    spans = chunk_word_spans(
        cleaned_document_text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )

    document_id = str(document_row["document_id"])
    classification = str(document_row.get("classification", "public"))
    allowed_roles = _normalise_allowed_roles(document_row.get("allowed_roles"))
    owner = str(document_row.get("owner", ""))
    department = str(document_row.get("department", ""))
    version = str(document_row.get("version", ""))
    source_path = str(document_row.get("source_path", ""))
    document_hash = str(document_row.get("document_hash", ""))

    return [
        {
            "chunk_id": _chunk_id(document_id, document_hash, chunk_index),
            "document_id": document_id,
            "chunk_index": chunk_index,
            "chunk_text": " ".join(words[start:end]),
            "chunk_span": (start, end),
            "classification": classification,
            "allowed_roles": allowed_roles,
            "owner": owner,
            "department": department,
            "version": version,
            "source_path": source_path,
            "document_hash": document_hash
        }
        for chunk_index, (start, end) in enumerate(spans)
    ]


def _chunk_id(document_id: str, document_hash: str, chunk_index: int) -> str:
    """Return a stable chunk identifier for repeatable cache lookups."""
    stable_key = f"{document_id}:{document_hash}:{chunk_index}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, stable_key))
