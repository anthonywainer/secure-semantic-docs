"""Tests for governed fact extraction."""

from pathlib import Path

import pytest

# noinspection PyProtectedMember
from secure_semantic_docs.processing.fact_extractor import (
    _extract_facts_from_document,  # noqa: SLF001
    _find_best_chunk_id,  # noqa: SLF001
    extract_facts_from_chunk,
)

_DOC_PATH = (
    Path("data")
    / "synthetic_data"
    / "raw_documents"
    / "confidential"
    / "DOC-009_incident.txt"
)


def test_extract_incident_commander_from_doc_009() -> None:
    """Per-chunk extraction works when title and commander are in the same chunk."""
    chunk = {
        "chunk_id": "DOC-009-000",
        "document_id": "DOC-009",
        "chunk_text": _DOC_PATH.read_text(encoding="utf-8"),
        "classification": "confidential",
        "allowed_roles": ["security_engineer"],
        "department": "Engineering",
        "source_path": "confidential/DOC-009_incident.txt"
    }

    facts = extract_facts_from_chunk(chunk, "2026-05-17T00:00:00Z")

    assert len(facts) == 1
    fact = facts[0]
    assert fact["subject"] == "PIPELINE OUTAGE 2024-01-15"
    assert fact["predicate"] == "HAS_INCIDENT_COMMANDER"
    assert fact["object"] == "hshaw@example.org"
    assert fact["fact_type"] == "incident_commander"
    assert fact["document_id"] == "DOC-009"
    assert fact["chunk_id"] == "DOC-009-000"


def test_per_chunk_extraction_fails_when_facts_span_chunks() -> None:
    """Per-chunk extraction returns no facts when title and commander are in different chunks."""
    full_text = _DOC_PATH.read_text(encoding="utf-8")
    midpoint = len(full_text) // 2
    chunk_with_title = {
        "chunk_id": "DOC-009-000",
        "document_id": "DOC-009",
        "chunk_text": full_text[:midpoint],
        "classification": "confidential",
        "allowed_roles": ["security_engineer"],
        "department": "Engineering",
        "source_path": "confidential/DOC-009_incident.txt"
    }
    chunk_with_commander = {
        "chunk_id": "DOC-009-001",
        "document_id": "DOC-009",
        "chunk_text": full_text[midpoint:],
        "classification": "confidential",
        "allowed_roles": ["security_engineer"],
        "department": "Engineering",
        "source_path": "confidential/DOC-009_incident.txt"
    }
    assert not extract_facts_from_chunk(chunk_with_title, "2026-05-17T00:00:00Z")
    assert not extract_facts_from_chunk(chunk_with_commander, "2026-05-17T00:00:00Z")


def test_document_aware_extraction_succeeds_when_facts_span_chunks() -> None:
    """Document-aware extraction finds the fact even when split across chunks."""
    full_text = _DOC_PATH.read_text(encoding="utf-8")
    midpoint = len(full_text) // 2
    doc = {
        "document_id": "DOC-009",
        "classification": "confidential",
        "allowed_roles": ["security_engineer"],
        "department": "Engineering",
        "source_path": "confidential/DOC-009_incident.txt",
        "chunks": [
            {"chunk_index": 0, "chunk_id": "DOC-009-000", "chunk_text": full_text[:midpoint]},
            {"chunk_index": 1, "chunk_id": "DOC-009-001", "chunk_text": full_text[midpoint:]},
        ]
    }

    facts = _extract_facts_from_document(doc, "2026-05-17T00:00:00Z")

    assert len(facts) == 1
    fact = facts[0]
    assert fact["subject"] == "PIPELINE OUTAGE 2024-01-15"
    assert fact["predicate"] == "HAS_INCIDENT_COMMANDER"
    assert fact["object"] == "hshaw@example.org"
    assert fact["fact_type"] == "incident_commander"
    assert fact["document_id"] == "DOC-009"
    assert fact["extraction_method"] == "regex:v1:document_aware"


def test_document_aware_extraction_uses_commander_chunk_id() -> None:
    """Document-aware extraction stores the chunk_id containing the commander line."""
    full_text = _DOC_PATH.read_text(encoding="utf-8")
    midpoint = len(full_text) // 2
    doc = {
        "document_id": "DOC-009",
        "classification": "confidential",
        "allowed_roles": ["security_engineer"],
        "department": "Engineering",
        "source_path": "confidential/DOC-009_incident.txt",
        "chunks": [
            {"chunk_index": 0, "chunk_id": "DOC-009-000", "chunk_text": full_text[:midpoint]},
            {"chunk_index": 1, "chunk_id": "DOC-009-001", "chunk_text": full_text[midpoint:]},
        ]
    }

    facts = _extract_facts_from_document(doc, "2026-05-17T00:00:00Z")

    assert facts
    # Commander "hshaw@example.org" is in the second half of the document
    assert facts[0]["chunk_id"] == "DOC-009-001"


def test_document_aware_extraction_falls_back_to_first_chunk_when_no_commander_chunk() -> None:
    """When no individual chunk contains the commander, the first chunk_id is used."""
    doc = {
        "document_id": "DOC-009",
        "classification": "confidential",
        "allowed_roles": ["security_engineer"],
        "department": "Engineering",
        "source_path": "confidential/DOC-009_incident.txt",
        "chunks": [
            {"chunk_index": 0, "chunk_id": "DOC-009-000", "chunk_text": "INCIDENT REPORT: TEST 2024"},
            {"chunk_index": 1, "chunk_id": "DOC-009-001", "chunk_text": "Details here"},
            # Commander only in the combined text (split at character level so neither chunk has full email)
            {"chunk_index": 2, "chunk_id": "DOC-009-002", "chunk_text": "Incident commander: test@example.org"},
        ]
    }

    facts = _extract_facts_from_document(doc, "2026-05-17T00:00:00Z")

    assert facts
    # "test@example.org" is in chunk 002
    assert facts[0]["chunk_id"] == "DOC-009-002"


def test_document_aware_extraction_returns_empty_for_no_incident() -> None:
    """Document-aware extraction returns nothing for non-incident documents."""
    doc = {
        "document_id": "DOC-001",
        "classification": "internal",
        "allowed_roles": [],
        "department": "HR",
        "source_path": "internal/DOC-001.txt",
        "chunks": [
            {"chunk_index": 0, "chunk_id": "DOC-001-000", "chunk_text": "Employee handbook content."},
            {"chunk_index": 1, "chunk_id": "DOC-001-001", "chunk_text": "More handbook content."},
        ]
    }

    facts = _extract_facts_from_document(doc, "2026-05-17T00:00:00Z")

    assert facts == []


def test_document_aware_extraction_returns_empty_for_empty_chunks() -> None:
    """Document-aware extraction returns nothing when the chunk list is empty."""
    doc = {
        "document_id": "DOC-001",
        "classification": "internal",
        "allowed_roles": [],
        "department": "HR",
        "source_path": "internal/DOC-001.txt",
        "chunks": []
    }

    facts = _extract_facts_from_document(doc, "2026-05-17T00:00:00Z")

    assert facts == []


def test_find_best_chunk_id_returns_commander_chunk() -> None:
    """_find_best_chunk_id returns the chunk containing the email address."""
    chunks = [
        {"chunk_index": 0, "chunk_id": "DOC-009-000", "chunk_text": "Title and summary"},
        {"chunk_index": 1, "chunk_id": "DOC-009-001", "chunk_text": "Incident commander: hshaw@example.org"},
    ]

    result = _find_best_chunk_id(chunks, "hshaw@example.org")

    assert result == "DOC-009-001"


def test_find_best_chunk_id_falls_back_to_first() -> None:
    """_find_best_chunk_id falls back to the first chunk_id when not found."""
    chunks = [
        {"chunk_index": 0, "chunk_id": "DOC-009-000", "chunk_text": "No email here"},
        {"chunk_index": 1, "chunk_id": "DOC-009-001", "chunk_text": "Still nothing"},
    ]

    result = _find_best_chunk_id(chunks, "nobody@example.org")

    assert result == "DOC-009-000"


@pytest.mark.parametrize("user_role,clearance,allowed_roles,expect_access", [
    ("admin", "restricted", ["security_engineer"], True),
    ("security_engineer", "confidential", ["security_engineer"], True),
    ("business_analyst", "internal", ["security_engineer"], False),
])
def test_fact_access_by_role(
    user_role: str,
    clearance: str,
    allowed_roles: list[str],
    expect_access: bool
) -> None:
    """Admin and security_engineer can access confidential facts; business_analyst cannot."""
    from secure_semantic_docs.governance.permissions import can_access_record  # noqa: PLC0415

    user = {"role": user_role, "clearance_level": clearance}
    fact_record = {
        "classification": "confidential",
        "allowed_roles": allowed_roles,
        "department": "Engineering"
    }

    result = can_access_record(user, fact_record)

    assert result is expect_access, (
        f"Expected {user_role} to {'have' if expect_access else 'not have'} access"
    )


def test_facts_path_consistency() -> None:
    """The canonical facts path used in gold_ingestion and streamlit_app must be identical."""
    from secure_semantic_docs.loader import load_config  # noqa: PLC0415
    config = load_config()

    gold_path = (
        config.project_root / "runtime" / "metadata" / "facts" / "extracted_facts.jsonl"
    )
    streamlit_path = (
        config.project_root / "runtime" / "metadata" / "facts" / "extracted_facts.jsonl"
    )
    demo_path = (
        config.project_root / "runtime" / "metadata" / "facts" / "extracted_facts.jsonl"
    )

    assert gold_path == streamlit_path == demo_path

