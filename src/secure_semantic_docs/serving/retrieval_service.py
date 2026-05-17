"""Secure retrieval service: filter-first, decrypt-second, search-third, audit-always."""

import json
import logging
import uuid as _uuid
from pathlib import Path
from typing import Any

import numpy as np

from secure_semantic_docs.core.settings import BaseSettings
from secure_semantic_docs.governance.audit import log_search_event
from secure_semantic_docs.governance.permissions import can_access_record
from secure_semantic_docs.serving.access_context import AccessContext
from secure_semantic_docs.serving.result_sanitizer import (
    get_gold_forbidden_fields,
    sanitize_result
)

logger = logging.getLogger(BaseSettings.APP_NAME)
NO_AUTHORIZED_INFORMATION = "No authorized information was found for your query."


def load_gold_records(gold_path: Path | str) -> list[dict]:
    """Load gold Parquet records for use as retrieval candidates.

    Parameters
    ----------
    gold_path
        Path to the gold_embeddings Parquet directory.

    Returns
    -------
    list[dict]
        Raw gold records including encrypted fields (needed for decryption).
    """
    gold_path = Path(gold_path)
    if not gold_path.exists():
        logger.warning("Gold path not found: %s", gold_path)
        return []
    try:
        import pandas as pd  # noqa: PLC0415
        parquet_files = list(gold_path.rglob("*.parquet"))
        if not parquet_files:
            return []
        df = pd.concat([pd.read_parquet(f) for f in parquet_files], ignore_index=True)
        return df.to_dict("records")
    except Exception as exc:
        logger.warning("Could not load gold records from %s: %s", gold_path, exc)
        return []


def load_fact_records(facts_path: Path | str) -> list[dict]:
    """Load extracted fact records from JSON Lines storage.

    Accepts both single-line JSONL and pretty-printed multi-line JSON objects,
    so that files written by older pipeline versions are still readable.
    """
    facts_path = Path(facts_path)
    if not facts_path.exists():
        logger.warning("Facts path not found: %s", facts_path)
        return []

    content = facts_path.read_text(encoding="utf-8").strip()
    if not content:
        return []

    records: list[dict] = []
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(content):
        while idx < len(content) and content[idx] in " \t\r\n":
            idx += 1
        if idx >= len(content):
            break
        obj, end = decoder.raw_decode(content, idx)
        records.append(obj)
        idx = end
    return records


def _candidate_id(candidate: dict[str, Any]) -> str:
    """Return the best identifier for a retrieval candidate."""
    return candidate.get('chunk_id') or candidate.get('document_id', 'unknown')


def _compute_query_embedding(
        query: str,
        model_name: str = 'all-MiniLM-L6-v2'
) -> np.ndarray | None:
    """Compute query embedding using SentenceTransformers."""
    try:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        model = SentenceTransformer(model_name)
        embedding = model.encode(query, normalize_embeddings=True, convert_to_numpy=True)
        return np.asarray(embedding, dtype=np.float32)
    except Exception as exc:
        logger.debug('Could not compute query embedding: %s', exc)
        return None


def _decrypt_embedding(record: dict, encryption_key: bytes) -> np.ndarray | None:
    """Decrypt an embedding record. Returns None on failure."""
    try:
        from secure_semantic_docs.security.secretbox_decryptor import secretbox_decrypt  # noqa: PLC0415
        ciphertext = record.get('embedding_ciphertext')
        nonce = record.get('embedding_nonce')
        if not isinstance(ciphertext, bytes | bytearray | memoryview) or not isinstance(nonce,
                                                                                        bytes | bytearray | memoryview):
            return None
        plaintext = secretbox_decrypt(bytes(ciphertext), bytes(nonce), encryption_key)
        return np.frombuffer(plaintext, dtype=np.float32)
    except Exception as exc:
        logger.debug(
            'Could not decrypt embedding for chunk_id=%s: %s',
            record.get('chunk_id'),
            exc
        )
        return None


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _rank_by_similarity(
        authorized: list[dict],
        query_embedding: np.ndarray | None,
        encryption_key: bytes | None
) -> tuple[list[dict], int]:
    """Rank authorized candidates by cosine similarity to query embedding.

    Returns sorted candidates and count of successfully decrypted embeddings.
    Falls back to original order when embedding decryption is unavailable.
    """
    if query_embedding is None or encryption_key is None:
        return authorized, 0

    scored = []
    decrypted_count = 0
    for candidate in authorized:
        vector = _decrypt_embedding(candidate, encryption_key)
        if vector is not None:
            decrypted_count += 1
            score = _cosine_similarity(query_embedding, vector)
        else:
            score = 0.0
        scored.append((score, candidate))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [candidate for _, candidate in scored], decrypted_count


def secure_retrieve(
        context: AccessContext,
        candidates: list[dict]
) -> dict[str, Any]:
    """Secure retrieval: filter first, decrypt second, search third, audit always.

    Parameters
    ----------
    context
        Access context with user, query, top_k, logs_dir, and optional key.
    candidates
        List of candidate gold records.

    Returns
    -------
    dict
        Result dict with results, access_granted, decrypted_count, filtered_out.
    """
    if not context.user:
        log_search_event(
            user_id=context.user_id,
            role='unknown',
            query=context.query,
            mode='secure',
            returned_ids=[],
            filtered_out_ids=[],
            access_decisions={},
            decrypted_embedding_count=0,
            status='denied',
            logs_dir=context.logs_dir
        )
        return {
            'results': [],
            'access_granted': False,
            'decrypted_count': 0,
            'error': f'User not found: {context.user_id}'
        }

    authorized = []
    filtered_out_ids = []
    access_decisions = {}

    for candidate in candidates:
        can_access = can_access_record(context.user, candidate)
        candidate_id = _candidate_id(candidate)
        access_decisions[candidate_id] = can_access
        if can_access:
            authorized.append(candidate)
        else:
            filtered_out_ids.append(candidate_id)

    query_embedding = _compute_query_embedding(context.query)
    ranked, decrypted_count = _rank_by_similarity(
        authorized,
        query_embedding,
        context.encryption_key
    )

    forbidden = get_gold_forbidden_fields()
    top_results = [sanitize_result(record, forbidden) for record in ranked[:context.top_k]]
    returned_ids = [_candidate_id(record) for record in top_results]

    log_search_event(
        user_id=context.user_id,
        role=context.role,
        query=context.query,
        mode='secure',
        returned_ids=returned_ids,
        filtered_out_ids=filtered_out_ids,
        access_decisions=access_decisions,
        decrypted_embedding_count=decrypted_count,
        status='success',
        logs_dir=context.logs_dir
    )

    return {
        'results': top_results,
        'access_granted': len(top_results) > 0,
        'decrypted_count': decrypted_count,
        'filtered_out': filtered_out_ids
    }


def fact_retrieve(
        context: AccessContext,
        facts: list[dict]
) -> dict[str, Any]:
    """Answer supported exact questions from governed extracted facts."""
    if not is_fact_query(context.query):
        return {
            "answer": "",
            "facts": [],
            "access_granted": False,
            "filtered_out": [],
            "handled": False
        }

    if not context.user:
        _audit_fact_retrieval(context, [], [], {}, "denied")
        return {
            "answer": NO_AUTHORIZED_INFORMATION,
            "facts": [],
            "access_granted": False,
            "filtered_out": [],
            "handled": True,
            "error": f"User not found: {context.user_id}"
        }

    matching_facts = _matching_incident_commander_facts(context.query, facts)

    if not matching_facts:
        _audit_fact_retrieval(context, [], [], {}, "success")
        return {
            "answer": NO_AUTHORIZED_INFORMATION,
            "facts": [],
            "access_granted": False,
            "filtered_out": [],
            "handled": True,
            "fact_found": False
        }

    authorized: list[dict] = []
    filtered_out_ids: list[str] = []
    access_decisions: dict[str, bool] = {}

    for fact in matching_facts:
        fact_id = str(fact.get("fact_id", ""))
        can_access = can_access_record(context.user, fact)
        access_decisions[fact_id] = can_access
        if can_access:
            authorized.append(fact)
        else:
            filtered_out_ids.append(fact_id)

    if not authorized:
        _audit_fact_retrieval(context, [], filtered_out_ids, access_decisions, "success")
        return {
            "answer": NO_AUTHORIZED_INFORMATION,
            "facts": [],
            "access_granted": False,
            "filtered_out": filtered_out_ids,
            "handled": True,
            "fact_found": True
        }

    fact = authorized[0]
    safe_fact = sanitize_result(fact, frozenset())
    _audit_fact_retrieval(
        context,
        [str(safe_fact.get("fact_id", ""))],
        filtered_out_ids,
        access_decisions,
        "success"
    )
    return {
        "answer": f"The incident commander was {safe_fact.get('object')}.",
        "facts": [safe_fact],
        "access_granted": True,
        "filtered_out": filtered_out_ids,
        "handled": True,
        "fact_found": True
    }


def insecure_retrieve(
        context: AccessContext,
        candidates: list[dict]
) -> dict[str, Any]:
    """Unsafe demo retrieval mode: marks but does not hide unauthorized results.

    **THIS IS DEMO ONLY. NEVER USE IN PRODUCTION.**

    Parameters
    ----------
    context
        Access context with user, query, top_k, logs_dir, and optional key.
    candidates
        List of candidate gold records.

    Returns
    -------
    dict
        Result dict with results, filtered_out, access_decisions, warning.
    """
    authorized = []
    filtered_out = []
    access_decisions = {}

    for candidate in candidates:
        can_access = can_access_record(context.user, candidate)
        candidate_id = _candidate_id(candidate)
        access_decisions[candidate_id] = can_access
        if can_access:
            authorized.append(candidate)
        else:
            filtered_out.append(candidate_id)

    query_embedding = _compute_query_embedding(context.query)
    ranked, decrypted_count = _rank_by_similarity(
        authorized,
        query_embedding,
        context.encryption_key
    )

    forbidden = get_gold_forbidden_fields()
    top_results = [sanitize_result(record, forbidden) for record in ranked[:context.top_k]]
    returned_ids = [_candidate_id(record) for record in top_results]

    log_search_event(
        user_id=context.user_id,
        role=context.role,
        query=context.query,
        mode='insecure',
        returned_ids=returned_ids,
        filtered_out_ids=filtered_out,
        access_decisions=access_decisions,
        decrypted_embedding_count=decrypted_count,
        status='success',
        logs_dir=context.logs_dir
    )

    return {
        "results": top_results,
        "filtered_out": filtered_out,
        "filtered_out_count": len(filtered_out),
        "access_decisions": access_decisions,
        "warning": "DEMO ONLY: This is unsafe search mode. Use secure_search for production."
    }


def is_fact_query(query: str) -> bool:
    """Return true when the query should be answered from extracted facts."""
    normalized = query.casefold()
    return (
            "incident commander" in normalized
            or "who was the incident commander" in normalized
    )


def _matching_incident_commander_facts(
        query: str,
        facts: list[dict]
) -> list[dict]:
    """Return incident commander facts matching the query subject."""
    if not is_fact_query(query):
        return []

    requested_subject = _extract_requested_incident_subject(query)
    matches: list[dict] = []
    for fact in facts:
        if fact.get("fact_type") != "incident_commander":
            continue
        subject = str(fact.get("subject", ""))
        if requested_subject and _normalize_fact_text(subject) != requested_subject:
            continue
        matches.append(fact)
    return matches


def _extract_requested_incident_subject(query: str) -> str:
    """Return the requested incident subject when the query names one."""
    normalized_query = _normalize_fact_text(query)
    marker = " incident commander of "
    if marker not in f" {normalized_query} ":
        return ""
    return normalized_query.split(marker, maxsplit=1)[1].strip()


def _normalize_fact_text(value: str) -> str:
    """Normalize fact/query text for deterministic rule matching."""
    return " ".join(value.casefold().replace("?", " ").split())


def _audit_fact_retrieval(
        context: AccessContext,
        returned_ids: list[str],
        filtered_out_ids: list[str],
        access_decisions: dict[str, bool],
        status: str
) -> None:
    """Write an audit event for fact retrieval."""
    log_search_event(
        user_id=context.user_id,
        role=context.role,
        query=context.query,
        mode="fact_retrieve",
        returned_ids=returned_ids,
        filtered_out_ids=filtered_out_ids,
        access_decisions=access_decisions,
        decrypted_embedding_count=0,
        status=status,
        logs_dir=context.logs_dir
    )


def _merge_candidates(
        primary: list[dict[str, Any]],
        secondary: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge two candidate lists, deduplicating by chunk_id.

    Primary candidates take precedence. Secondary fills in any not already present.

    Parameters
    ----------
    primary
        Higher-priority candidate list.
    secondary
        Lower-priority candidate list.

    Returns
    -------
    list[dict[str, Any]]
        Deduplicated merged list, primary first.
    """
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for candidate in primary:
        candidate_id = _candidate_id(candidate)
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        merged.append(candidate)
    for candidate in secondary:
        candidate_id = _candidate_id(candidate)
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        merged.append(candidate)
    return merged


def build_text_model_context(
        authorized_results: list[dict[str, Any]],
        query: str,
        user: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build a context bundle for future text model integration.

    Text model integration is disabled by default and must be explicitly enabled.
    Only authorized, sanitized results are included. No raw ciphertexts,
    no embedding nonces, no decrypted embeddings, no decrypted chunk text.

    Parameters
    ----------
    authorized_results
        Sanitized authorized result records (must not contain plaintext text).
    query
        The original user query.
    user
        Authenticated user record for audit context.

    Returns
    -------
    dict[str, Any]
        Context bundle with query, authorized_sources, user_role, and
        a disabled flag indicating text model integration is off.
    """
    return {
        "query": query,
        "text_model_enabled": False,
        "authorized_sources": [
            {
                "chunk_id": result.get("chunk_id", ""),
                "document_id": result.get("document_id", ""),
                "classification": result.get("classification", ""),
                "owner": result.get("owner", ""),
                "department": result.get("department", "")
            }
            for result in authorized_results
        ],
        "user_role": user.get("role", "unknown") if user else "unknown",
        "source_count": len(authorized_results),
        "note": (
            "Text model integration is disabled by default. "
            "Only authorized context is prepared here. "
            "Enable explicitly and ensure only authorized sources are passed."
        )
    }


_NO_FACT_ANSWER_WITH_CANDIDATES = (
    "Authorized semantic candidates were found, but no extracted fact answer "
    "is available for this query."
)


def governed_retrieve(
        context: AccessContext,
        candidates: list[dict],
        facts: list[dict]
) -> dict[str, Any]:
    """Governed retrieval combining fact lookup and semantic search.

    Tries fact retrieval first for exact questions, then falls back to
    semantic search. Always returns a normalized user-facing result shape
    — never exposes raw records or JSON as the main answer.

    Parameters
    ----------
    context
        Access context with user, query, top_k, logs_dir, and optional key.
    candidates
        Gold record candidates for semantic search.
    facts
        Extracted fact records for exact question answering.

    Returns
    -------
    dict[str, Any]
        Normalized result with keys: answer, answer_type, status, strategy,
        sources, blocked_count, audit_request_id, technical_details.

        Possible status values: answered, no_authorized_information,
        no_fact_answer, error.

        Possible answer_type values: fact_answer, candidate_list,
        no_fact_answer, no_answer, error.
    """
    audit_request_id = str(_uuid.uuid4())

    fact_result = fact_retrieve(context, facts)
    if fact_result.get("handled"):
        if fact_result.get("access_granted"):
            return _build_fact_governed_result(fact_result, audit_request_id)

        if fact_result.get("fact_found"):
            return {
                "answer": NO_AUTHORIZED_INFORMATION,
                "answer_type": "no_answer",
                "status": "no_authorized_information",
                "strategy": "fact_lookup",
                "sources": [],
                "blocked_count": len(fact_result.get("filtered_out", [])),
                "audit_request_id": audit_request_id,
                "technical_details": {}
            }

        return _semantic_fallback_for_fact_query(context, candidates, audit_request_id)

    return _full_semantic_retrieve(context, candidates, audit_request_id)


def _build_fact_governed_result(
        fact_result: dict[str, Any],
        audit_request_id: str
) -> dict[str, Any]:
    """Build a normalized governed result from a successful fact_retrieve response."""
    sources = [
        {
            "document_id": f.get("document_id", ""),
            "chunk_id": f.get("chunk_id", ""),
            "classification": f.get("classification", "")
        }
        for f in fact_result.get("facts", [])
    ]
    return {
        "answer": fact_result["answer"],
        "answer_type": "fact_answer",
        "status": "answered",
        "strategy": "fact_lookup",
        "sources": sources,
        "blocked_count": len(fact_result.get("filtered_out", [])),
        "audit_request_id": audit_request_id,
        "technical_details": {}
    }


def _semantic_fallback_for_fact_query(
        context: AccessContext,
        candidates: list[dict],
        audit_request_id: str
) -> dict[str, Any]:
    """Try semantic search as fallback when a fact query matched no stored fact."""
    if not candidates:
        return {
            "answer": NO_AUTHORIZED_INFORMATION,
            "answer_type": "no_answer",
            "status": "no_authorized_information",
            "strategy": "fact_lookup",
            "sources": [],
            "blocked_count": 0,
            "audit_request_id": audit_request_id,
            "technical_details": {}
        }

    semantic_result = secure_retrieve(context, candidates)
    top_results = semantic_result.get("results", [])
    blocked_count = len(semantic_result.get("filtered_out", []))

    if not top_results:
        return {
            "answer": NO_AUTHORIZED_INFORMATION,
            "answer_type": "no_answer",
            "status": "no_authorized_information",
            "strategy": "hybrid",
            "sources": [],
            "blocked_count": blocked_count,
            "audit_request_id": audit_request_id,
            "technical_details": {}
        }

    return {
        "answer": _NO_FACT_ANSWER_WITH_CANDIDATES,
        "answer_type": "no_fact_answer",
        "status": "no_fact_answer",
        "strategy": "hybrid",
        "sources": _extract_sources(top_results),
        "blocked_count": blocked_count,
        "audit_request_id": audit_request_id,
        "technical_details": {}
    }


def _full_semantic_retrieve(
        context: AccessContext,
        candidates: list[dict],
        audit_request_id: str
) -> dict[str, Any]:
    """Run full semantic retrieval for non-fact queries."""
    if not candidates:
        return {
            "answer": NO_AUTHORIZED_INFORMATION,
            "answer_type": "no_answer",
            "status": "no_authorized_information",
            "strategy": "semantic",
            "sources": [],
            "blocked_count": 0,
            "audit_request_id": audit_request_id,
            "technical_details": {}
        }

    semantic_result = secure_retrieve(context, candidates)
    top_results = semantic_result.get("results", [])
    blocked_count = len(semantic_result.get("filtered_out", []))

    if not top_results:
        return {
            "answer": NO_AUTHORIZED_INFORMATION,
            "answer_type": "no_answer",
            "status": "no_authorized_information",
            "strategy": "semantic",
            "sources": [],
            "blocked_count": blocked_count,
            "audit_request_id": audit_request_id,
            "technical_details": {}
        }

    return {
        "answer": "Authorized semantic candidates were found. Review the sources below.",
        "answer_type": "candidate_list",
        "status": "answered",
        "strategy": "semantic",
        "sources": _extract_sources(top_results),
        "blocked_count": blocked_count,
        "audit_request_id": audit_request_id,
        "technical_details": {}
    }


def _extract_sources(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract a safe, minimal source list from sanitized result records."""
    return [
        {
            "document_id": r.get("document_id", ""),
            "chunk_id": r.get("chunk_id", ""),
            "classification": r.get("classification", ""),
            "score": r.get("score", ""),
            "source_path": r.get("source_path", "")
        }
        for r in results
    ]
