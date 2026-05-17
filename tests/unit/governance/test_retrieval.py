"""Tests for enhanced retrieval module with cosine similarity and field sanitization."""

from pathlib import Path
from typing import Any


# noinspection PyProtectedMember
from secure_semantic_docs.governance.retrieval import (
    _sanitize_result,  # noqa: SLF001
    insecure_search,
    secure_search,
)

_PUBLIC_CHUNK: dict[str, Any] = {
    "chunk_id": "DOC-022-1",
    "document_id": "DOC-022",
    "title": "PySpark Best Practices",
    "classification": "public",
    "allowed_roles": [],
    "department": "Data Platform",
    "embedding_ciphertext": b"fakeciphertext",
    "embedding_nonce": b"fakenonce",
    "key_id": "key-001"
}

_CONFIDENTIAL_SECURITY_CHUNK: dict[str, Any] = {
    "chunk_id": "DOC-008-1",
    "document_id": "DOC-008",
    "title": "Security Audit",
    "classification": "confidential",
    "allowed_roles": ["security_engineer", "compliance_officer"],
    "department": "security",
    "embedding_ciphertext": b"fakeciphertext2",
    "embedding_nonce": b"fakenonce2",
    "key_id": "key-001"
}

_RESTRICTED_FINANCE_CHUNK: dict[str, Any] = {
    "chunk_id": "DOC-010-1",
    "document_id": "DOC-010",
    "title": "Payroll Policy",
    "classification": "restricted",
    "allowed_roles": ["finance_manager", "hr_manager"],
    "department": "Finance",
    "embedding_ciphertext": b"fakeciphertext3",
    "embedding_nonce": b"fakenonce3",
    "key_id": "key-001"
}

_CANDIDATES = [_PUBLIC_CHUNK, _CONFIDENTIAL_SECURITY_CHUNK, _RESTRICTED_FINANCE_CHUNK]

_USERS = {
    "business_analyst": {
        "user_id": "business_analyst",
        "role": "business_analyst",
        "department": "business",
        "clearance_level": "internal"
    },
    "security_engineer": {
        "user_id": "security_engineer",
        "role": "security_engineer",
        "department": "security",
        "clearance_level": "confidential"
    },
    "external_viewer": {
        "user_id": "external_viewer",
        "role": "external_viewer",
        "department": "external",
        "clearance_level": "public"
    },
    "finance_manager": {
        "user_id": "finance_manager",
        "role": "finance_manager",
        "department": "Finance",
        "clearance_level": "restricted"
    }
}


def test_business_analyst_cannot_access_confidential_security_chunks(tmp_path: Path):
    """Business analyst must not see confidential security chunks."""
    result = secure_search(
        query="security audit",
        user_id="business_analyst",
        candidates=_CANDIDATES,
        top_k=10,
        users=_USERS,
        logs_dir=tmp_path
    )
    returned_ids = [r.get("chunk_id") for r in result["results"]]
    assert "DOC-008-1" not in returned_ids
    assert "DOC-010-1" not in returned_ids


def test_security_engineer_can_access_confidential_security_chunks(tmp_path: Path):
    """Security engineer should see confidential security chunks."""
    result = secure_search(
        query="security audit",
        user_id="security_engineer",
        candidates=_CANDIDATES,
        top_k=10,
        users=_USERS,
        logs_dir=tmp_path
    )
    returned_ids = [r.get("chunk_id") for r in result["results"]]
    assert "DOC-008-1" in returned_ids


def test_external_viewer_sees_only_public(tmp_path: Path):
    """External viewer can only access public records."""
    result = secure_search(
        query="public documents",
        user_id="external_viewer",
        candidates=_CANDIDATES,
        top_k=10,
        users=_USERS,
        logs_dir=tmp_path
    )
    for record in result["results"]:
        assert record.get("classification") == "public"


def test_secure_search_filters_before_returning(tmp_path: Path):
    """Secure search must not return unauthorized records in results."""
    result = secure_search(
        query="all documents",
        user_id="external_viewer",
        candidates=_CANDIDATES,
        top_k=10,
        users=_USERS,
        logs_dir=tmp_path
    )
    assert len(result["results"]) == 1
    assert len(result["filtered_out"]) == 2


def test_secure_search_strips_sensitive_fields(tmp_path: Path):
    """Secure search results must not contain embedding_ciphertext, nonce, or key_id."""
    result = secure_search(
        query="public",
        user_id="external_viewer",
        candidates=_CANDIDATES,
        top_k=10,
        users=_USERS,
        logs_dir=tmp_path
    )
    for record in result["results"]:
        assert "embedding_ciphertext" not in record
        assert "embedding_nonce" not in record
        assert "key_id" not in record


def test_insecure_search_does_not_reveal_unauthorized_content(tmp_path: Path):
    """Insecure search must not expose content of unauthorized records."""
    result = insecure_search(
        query="all documents",
        user_id="external_viewer",
        candidates=_CANDIDATES,
        top_k=10,
        users=_USERS,
        logs_dir=tmp_path
    )
    returned_ids = [r.get("chunk_id") for r in result["results"]]
    for blocked_id in result["filtered_out"]:
        assert blocked_id not in returned_ids


def test_insecure_search_strips_sensitive_fields(tmp_path: Path):
    """Insecure search results must not contain sensitive fields."""
    result = insecure_search(
        query="public documents",
        user_id="external_viewer",
        candidates=_CANDIDATES,
        top_k=10,
        users=_USERS,
        logs_dir=tmp_path
    )
    for record in result["results"]:
        assert "embedding_ciphertext" not in record
        assert "embedding_nonce" not in record
        assert "key_id" not in record


def test_secure_search_writes_audit_log(tmp_path: Path):
    """Secure search must write an audit event."""
    import json
    secure_search(
        query="test",
        user_id="external_viewer",
        candidates=_CANDIDATES,
        top_k=5,
        users=_USERS,
        logs_dir=tmp_path
    )
    audit_path = tmp_path / "audit_log.jsonl"
    assert audit_path.exists()
    with audit_path.open() as f:
        event = json.loads(f.readline())
    assert event["event_type"] == "search"
    assert event["mode"] == "secure"
    assert event["user_id"] == "external_viewer"


def test_secure_search_unknown_user_denied(tmp_path: Path):
    """Secure search denies access for unknown user."""
    result = secure_search(
        query="test",
        user_id="not_a_real_user",
        candidates=_CANDIDATES,
        top_k=5,
        users=_USERS,
        logs_dir=tmp_path
    )
    assert result["access_granted"] is False
    assert result["results"] == []


def test_sanitize_result_removes_forbidden_fields():
    """_sanitize_result must strip embedding_ciphertext, nonce, and key_id."""
    record = {
        "chunk_id": "DOC-001-1",
        "classification": "public",
        "embedding_ciphertext": b"abc",
        "embedding_nonce": b"nonce",
        "key_id": "key-001",
        "title": "Test"
    }
    sanitized = _sanitize_result(record)
    assert "embedding_ciphertext" not in sanitized
    assert "embedding_nonce" not in sanitized
    assert "key_id" not in sanitized
    assert sanitized["chunk_id"] == "DOC-001-1"
    assert sanitized["title"] == "Test"
