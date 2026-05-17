"""Backward-compatible retrieval API.

All retrieval logic now lives in :mod:`secure_semantic_docs.serving.retrieval_service`.
This module re-exports the public API for backward compatibility.
"""

import logging
from pathlib import Path
from typing import Any

from secure_semantic_docs.core.settings import BaseSettings
from secure_semantic_docs.serving.access_context import AccessContext
from secure_semantic_docs.serving.retrieval_service import (
    fact_retrieve,
    governed_retrieve,
    insecure_retrieve,
    load_fact_records as _load_fact_records_impl,
    load_gold_records as _load_gold_records_impl,
    secure_retrieve
)

logger = logging.getLogger(BaseSettings.APP_NAME)

_SENSITIVE_FIELDS = frozenset({
    'embedding_ciphertext',
    'embedding_nonce',
    'key_id'
})


def _sanitize_result(record: dict) -> dict:
    """Strip sensitive fields from a result record before returning to UI."""
    from secure_semantic_docs.serving.result_sanitizer import (  # noqa: PLC0415
        sanitize_result as _sanitize_result_impl
    )
    return _sanitize_result_impl(record, _SENSITIVE_FIELDS)


def load_gold_records(gold_path: Path | str) -> list[dict]:
    """Load gold records via the canonical serving retrieval module."""
    return _load_gold_records_impl(gold_path)


def load_fact_records(facts_path: Path | str) -> list[dict]:
    """Load extracted fact records via the canonical serving retrieval module."""
    return _load_fact_records_impl(facts_path)


def secure_search(
        query: str,
        user_id: str,
        candidates: list[dict],
        top_k: int = 5,
        users: dict[str, dict] | None = None,
        logs_dir: Path | str = 'runtime/logs',
        encryption_key: bytes | None = None
) -> dict[str, Any]:
    """Secure retrieval: filter first, decrypt second, search third, audit always.

    .. deprecated::
        Use :func:`secure_semantic_docs.serving.retrieval_service.secure_retrieve` directly.
    """
    if users is None:
        users = {}
    user = users.get(user_id)
    context = AccessContext(
        user=user,
        user_id=user_id,
        query=query,
        top_k=top_k,
        logs_dir=Path(logs_dir),
        encryption_key=encryption_key
    )
    return secure_retrieve(context, candidates)


def fact_search(
        query: str,
        user_id: str,
        facts: list[dict],
        users: dict[str, dict] | None = None,
        logs_dir: Path | str = 'runtime/logs'
) -> dict[str, Any]:
    """Answer supported exact questions from extracted facts."""
    if users is None:
        users = {}
    user = users.get(user_id)
    context = AccessContext(
        user=user,
        user_id=user_id,
        query=query,
        top_k=1,
        logs_dir=Path(logs_dir)
    )
    return fact_retrieve(context, facts)


def insecure_search(
        query: str,
        user_id: str,
        candidates: list[dict],
        top_k: int = 5,
        users: dict[str, dict] | None = None,
        logs_dir: Path | str = 'runtime/logs',
        encryption_key: bytes | None = None
) -> dict[str, Any]:
    """Unsafe demo search mode.

    .. deprecated::
        Use :func:`secure_semantic_docs.serving.retrieval_service.insecure_retrieve` directly.
    """
    if users is None:
        users = {}
    user = users.get(user_id)
    context = AccessContext(
        user=user,
        user_id=user_id,
        query=query,
        top_k=top_k,
        logs_dir=Path(logs_dir),
        encryption_key=encryption_key
    )
    return insecure_retrieve(context, candidates)


def governed_search(
        query: str,
        user_id: str,
        candidates: list[dict],
        facts: list[dict],
        top_k: int = 5,
        users: dict[str, dict] | None = None,
        logs_dir: Path | str = 'runtime/logs',
        encryption_key: bytes | None = None
) -> dict[str, Any]:
    """Governed retrieval returning a normalized user-facing result shape.

    Combines fact lookup and semantic search. Always returns a structured
    result with answer, status, sources, and retrieval details — never
    exposes raw records or JSON as the main answer.

    Parameters
    ----------
    query
        Natural language search query.
    user_id
        Authenticated user identifier.
    candidates
        Gold record candidates for semantic search.
    facts
        Extracted fact records for exact question answering.
    top_k
        Maximum number of semantic results to consider.
    users
        Mapping of user_id to user record.
    logs_dir
        Directory for audit log output.
    encryption_key
        Optional symmetric key for embedding decryption.

    Returns
    -------
    dict[str, Any]
        Normalized result with keys: answer, answer_type, status, strategy,
        sources, blocked_count, audit_request_id, technical_details.
    """
    if users is None:
        users = {}
    user = users.get(user_id)
    context = AccessContext(
        user=user,
        user_id=user_id,
        query=query,
        top_k=top_k,
        logs_dir=Path(logs_dir),
        encryption_key=encryption_key
    )
    return governed_retrieve(context, candidates, facts)
