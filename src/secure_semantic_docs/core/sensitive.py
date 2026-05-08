"""Synthetic sensitive information detection for the silver layer.

This module is a **demo-level simulation** of PII and sensitive content
detection. It is not a production-grade PII engine. All patterns are
intentionally simple and tuned for the synthetic dataset produced by the
data generator.
"""

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass

from secure_semantic_docs.core import BaseSettings

logger = logging.getLogger(BaseSettings.APP_NAME)

_SECURITY_KEYWORDS: frozenset[str] = frozenset({
    "vulnerability",
    "incident",
    "audit finding",
    "secret",
    "token",
    "credential",
    "payroll",
    "contract",
    "pentest",
    "penetration test",
    "exploit",
    "breach"
})

_PATTERN_MAP: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "employee_id": re.compile(r"\bEMP-\d{6}\b"),
    "client_id": re.compile(r"\bCLT-[A-Z]{2}-\d{5}\b"),
    "project_code": re.compile(r"\bPROJ-[A-Z]{3}-\d{3}\b"),
    "financial_amount": re.compile(r"\$[\d,]+\.\d{2}\b"),
    "token": re.compile(r"\btok_[a-f0-9]{16,}\b")
}

_KEYWORD_TYPE_MAP: dict[str, str] = {
    kw: f"keyword:{kw.replace(' ', '_')}" for kw in _SECURITY_KEYWORDS
}

_KEYWORDS_PATTERN: re.Pattern[str] = re.compile(
    "|".join(re.escape(kw) for kw in sorted(_SECURITY_KEYWORDS, key=len, reverse=True)),
    re.IGNORECASE
)

_CLASSIFICATION_BASE_SCORE: dict[str, float] = {
    "public": 0.0,
    "internal": 0.1,
    "confidential": 0.4,
    "restricted": 0.6
}


@dataclass(frozen=True)
class SensitivityResult:
    """Result of a sensitivity analysis for a single chunk."""

    sensitivity_score: float
    detected_sensitive_types: list[str]
    requires_encryption: bool
    requires_restricted_access: bool


def analyse_chunk(text: str, classification: str) -> SensitivityResult:
    """Analyse *text* for sensitive patterns and return a :class:`SensitivityResult`.

    Uses a single compiled alternation regex for keyword detection and a set
    for O(1) deduplication. The returned ``detected_sensitive_types`` list is
    sorted for deterministic output.
    """
    detected: set[str] = {
        sensitive_type
        for sensitive_type, pattern in _PATTERN_MAP.items()
        if pattern.search(text)
    }

    for match in _KEYWORDS_PATTERN.finditer(text):
        detected.add(_KEYWORD_TYPE_MAP[match.group().lower()])

    classification_score = _CLASSIFICATION_BASE_SCORE.get(classification, 0.0)
    pattern_score = min(len(detected) * 0.1, 0.5)
    score = round(min(classification_score + pattern_score, 1.0), 3)

    return SensitivityResult(
        sensitivity_score=score,
        detected_sensitive_types=sorted(detected),
        requires_encryption=score >= 0.5,
        requires_restricted_access=score >= 0.7
    )


def enrich_chunks_with_sensitivity(
        chunk_payloads: list[Mapping[str, object]]
) -> list[dict[str, object]]:
    """Add sensitivity fields to a list of chunk dictionaries."""
    enriched_chunk_payloads: list[dict[str, object]] = []
    chunk_count = 0
    for chunk_payload in chunk_payloads:
        result = analyse_chunk(
            str(chunk_payload.get("chunk_text", "") or ""),
            str(chunk_payload.get("classification", "public"))
        )
        enriched_chunk_payloads.append(
            {
                **chunk_payload,
                "sensitivity_score": result.sensitivity_score,
                "detected_sensitive_types": result.detected_sensitive_types,
                "requires_encryption": result.requires_encryption,
                "requires_restricted_access": result.requires_restricted_access
            }
        )
        chunk_count += 1
    logger.info("Enriched %d chunks with sensitivity metadata.", chunk_count)
    return enriched_chunk_payloads
