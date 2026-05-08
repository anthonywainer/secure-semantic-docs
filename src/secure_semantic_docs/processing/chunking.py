"""Chunking and text normalization helpers for the silver pipeline."""

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
    """Single silver-layer chunk payload prior to sensitivity enrichment."""

    chunk_id: str
    document_id: str
    chunk_index: int
    chunk_text: str
    classification: str
    allowed_roles: list[str]
    owner: str
    department: str
    version: str
    source_path: str
    document_hash: str


type SensitiveSilverChunkRow = tuple[
    str,
    str,
    int,
    str,
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
    bool
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

    source_words = document_text.split()
    total_words = len(source_words)
    if not total_words:
        return []

    chunk_step = chunk_size - chunk_overlap
    text_chunks: list[str] = []
    chunk_start_index = 0
    while chunk_start_index < total_words:
        chunk_end_index = min(chunk_start_index + chunk_size, total_words)
        text_chunks.append(" ".join(source_words[chunk_start_index:chunk_end_index]))
        if chunk_end_index == total_words:
            break
        chunk_start_index += chunk_step
    return text_chunks


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


def _normalise_allowed_roles(allowed_roles_value: object) -> list[str]:
    """Convert a raw allowed_roles field into a list of strings."""
    if allowed_roles_value is None:
        return []
    if isinstance(allowed_roles_value, str):
        return [allowed_roles_value]
    if isinstance(allowed_roles_value, Iterable):
        return [str(role) for role in allowed_roles_value]
    return []  # pragma: no cover


def chunk_document(
        bronze_document_row: dict[str, object], chunk_size: int, chunk_overlap: int
) -> list[ChunkRecord]:
    """Produce all chunks for a single bronze-layer row."""
    cleaned_document_text = clean_text(str(bronze_document_row.get("raw_text", "") or ""))
    text_chunk_segments = chunk_text(
        cleaned_document_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )

    document_id = str(bronze_document_row["document_id"])
    classification = str(bronze_document_row.get("classification", "public"))
    allowed_roles = _normalise_allowed_roles(bronze_document_row.get("allowed_roles"))
    owner = str(bronze_document_row.get("owner", ""))
    department = str(bronze_document_row.get("department", ""))
    version = str(bronze_document_row.get("version", ""))
    source_path = str(bronze_document_row.get("source_path", ""))
    document_hash = str(bronze_document_row.get("document_hash", ""))

    return [
        {
            "chunk_id": str(uuid.uuid7()),
            "document_id": document_id,
            "chunk_index": chunk_index,
            "chunk_text": chunk_text_segment,
            "classification": classification,
            "allowed_roles": allowed_roles,
            "owner": owner,
            "department": department,
            "version": version,
            "source_path": source_path,
            "document_hash": document_hash
        }
        for chunk_index, chunk_text_segment in enumerate(text_chunk_segments)
    ]
