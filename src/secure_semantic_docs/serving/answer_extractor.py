"""Deterministic answer extraction from authorized decrypted chunk text.

Extracts structured answers from free-form document chunks by matching
known patterns for common question intents. No external model or LLM is
called — extraction is rule-based and auditable.

Only authorized, decrypted chunks are accepted as input. Callers must
ensure permission filtering and decryption have already been applied.
"""

from __future__ import annotations

import re

_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "incident_commander": [
        re.compile(r"[Ii]ncident\s+[Cc]ommander\s*[:=]\s*(\S+)"),
        re.compile(r"\bIC\s*[:=]\s*(\S+)"),
        re.compile(r"\b[Cc]ommander\s*[:=]\s*(\S+)"),
    ],
    "owner": [
        re.compile(r"\b[Oo]wner\s*[:=]\s*(.+?)(?:\n|$)"),
    ],
    "department": [
        re.compile(r"\b[Dd]epartment\s*[:=]\s*(.+?)(?:\n|$)"),
    ],
    "affected_system": [
        re.compile(r"[Aa]ffected\s+[Ss]ystem\s*[:=]\s*(.+?)(?:\n|$)"),
    ],
}

_QUERY_KEYWORDS: dict[str, list[str]] = {
    "incident_commander": ["incident commander", "commander", " ic "],
    "owner": ["owner"],
    "department": ["department"],
    "affected_system": ["affected system"],
}

_ANSWER_TEMPLATES: dict[str, str] = {
    "incident_commander": "The incident commander was {value}.",
    "owner": "The owner is {value}.",
    "department": "The department is {value}.",
    "affected_system": "The affected system is {value}.",
}

NO_AUTHORIZED_ANSWER = "No authorized information was found for your query."
NO_FACT_ANSWER = "No extracted fact answer is available for this query."

_NO_ANSWER = NO_AUTHORIZED_ANSWER


def build_fact_answer(_query: str, fact: dict) -> str:
    """Build a natural language answer from a structured fact record.

    Selects the answer template based on the fact's ``fact_type`` field.
    Falls back to a generic form when no template matches.

    Parameters
    ----------
    _query
        The original user query (reserved for future intent-aware formatting).
    fact
        Authorized fact record containing at least ``fact_type`` and ``object``.

    Returns
    -------
    str
        A formatted human-readable answer sentence.
    """
    fact_type = fact.get("fact_type", "")
    template = _ANSWER_TEMPLATES.get(fact_type)
    if template:
        return template.format(value=str(fact.get("object", "")).strip())
    return f"The answer is {fact.get('object', '')}."


def build_no_authorized_answer() -> str:
    """Return the standard no-authorized-information message."""
    return NO_AUTHORIZED_ANSWER


def build_no_fact_answer() -> str:
    """Return the standard no-fact-answer message."""
    return NO_FACT_ANSWER


def extract_answer(query: str, decrypted_chunks: list[dict]) -> str:
    """Extract a deterministic answer from authorized decrypted chunks.

    Detects the query intent from keyword matching, then applies the
    corresponding regex patterns against each chunk's ``chunk_text``.
    Returns the first match formatted as a human-readable sentence.

    Parameters
    ----------
    query:
        The original user query string.
    decrypted_chunks:
        List of records that include a ``chunk_text`` field containing
        the decrypted body. All records must be pre-authorized.

    Returns
    -------
    str
        A formatted answer sentence, or ``_NO_ANSWER`` when no match is found.
    """
    intent = _detect_intent(query)
    if intent is None:
        return _keyword_search(query, decrypted_chunks)

    patterns = _PATTERNS[intent]
    template = _ANSWER_TEMPLATES[intent]

    for chunk in decrypted_chunks:
        text = chunk.get("chunk_text", "")
        value = _first_match(patterns, text)
        if value:
            return template.format(value=value.strip())

    return _NO_ANSWER


def _detect_intent(query: str) -> str | None:
    """Return the intent key for *query*, or *None* when unknown."""
    lower = query.lower()
    for intent, keywords in _QUERY_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            return intent
    return None


def _first_match(patterns: list[re.Pattern[str]], text: str) -> str | None:
    """Return the first capture group from any pattern that matches *text*."""
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _keyword_search(query: str, decrypted_chunks: list[dict]) -> str:
    """Return a plain-text excerpt for keyword-based queries with no intent.

    Searches each chunk text for the query words and returns a brief
    confirmation when any chunk contains relevant content.
    """
    query_words = {w.lower() for w in query.split() if len(w) > 3}
    for chunk in decrypted_chunks:
        text = chunk.get("chunk_text", "").lower()
        if query_words and all(word in text for word in query_words):
            doc_id = chunk.get("document_id", "unknown")
            return f"Relevant content found in document {doc_id}."
    return _NO_ANSWER
