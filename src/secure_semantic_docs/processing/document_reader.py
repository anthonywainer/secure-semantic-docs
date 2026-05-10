"""Document text and word loading utilities."""

from __future__ import annotations

import logging
import pathlib

from secure_semantic_docs.core import BaseSettings
from secure_semantic_docs.processing.chunking import clean_text

logger = logging.getLogger(BaseSettings.APP_NAME)


def read_document_text(source_path: str, raw_docs_dir: str) -> str:
    """Read the raw text of a document file.

    Searches *raw_docs_dir* recursively for the filename component of
    *source_path*. Returns an empty string and logs a warning on failure.
    """
    base = pathlib.Path(raw_docs_dir)
    relative_path = pathlib.Path(source_path)
    direct_path = base / relative_path
    if direct_path.exists():
        return _read_text(direct_path)

    filename = relative_path.name
    matches = list(base.rglob(filename))
    if not matches:
        logger.warning(
            "Cannot read document file: %s (source_path=%s)",
            base / filename,
            source_path
        )
        return ""
    return _read_text(matches[0])


def _read_text(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        logger.warning(
            "Cannot read document file: %s", path
        )
        return ""


def read_document_words(source_path: str, raw_docs_dir: str) -> list[str]:
    """Return the cleaned, split word list for a document.

    Applies the same :func:`~secure_semantic_docs.processing.chunking.clean_text`
    transform used during silver processing so that gold can reconstruct
    the exact same text from word indices.
    """
    return clean_text(read_document_text(source_path, raw_docs_dir)).split()
