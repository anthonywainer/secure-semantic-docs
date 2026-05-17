"""Tests for retrieval_service using AccessContext."""

from pathlib import Path
from typing import Any

from secure_semantic_docs.serving.access_context import AccessContext
from secure_semantic_docs.serving.retrieval_service import (
    fact_retrieve,
    governed_retrieve,
    insecure_retrieve,
    secure_retrieve
)

_PUBLIC_CHUNK: dict[str, Any] = {
    'chunk_id': 'DOC-022-1',
    'document_id': 'DOC-022',
    'classification': 'public',
    'allowed_roles': [],
    'department': 'Data Platform',
    'embedding_ciphertext': b'fakeciphertext',
    'embedding_nonce': b'fakenonce',
    'key_id': 'key-001'
}

_CONFIDENTIAL_CHUNK: dict[str, Any] = {
    'chunk_id': 'DOC-008-1',
    'document_id': 'DOC-008',
    'classification': 'confidential',
    'allowed_roles': ['security_engineer'],
    'department': 'security',
    'embedding_ciphertext': b'fakeciphertext2',
    'embedding_nonce': b'fakenonce2',
    'key_id': 'key-001'
}

_CANDIDATES = [_PUBLIC_CHUNK, _CONFIDENTIAL_CHUNK]

_SECURITY_ENGINEER = {
    'user_id': 'security_engineer',
    'role': 'security_engineer',
    'department': 'security',
    'clearance_level': 'confidential'
}

_ADMIN = {
    'user_id': 'admin',
    'role': 'admin',
    'department': 'platform',
    'clearance_level': 'restricted'
}

_BUSINESS_ANALYST = {
    'user_id': 'business_analyst',
    'role': 'business_analyst',
    'department': 'business',
    'clearance_level': 'internal'
}

_EXTERNAL_VIEWER = {
    'user_id': 'external_viewer',
    'role': 'external_viewer',
    'department': 'external',
    'clearance_level': 'public'
}

_INCIDENT_FACT: dict[str, Any] = {
    "fact_id": "fact-incident-commander",
    "fact_type": "incident_commander",
    "subject": "PIPELINE OUTAGE 2024-01-15",
    "predicate": "HAS_INCIDENT_COMMANDER",
    "object": "hshaw@example.org",
    "document_id": "DOC-009",
    "chunk_id": "DOC-009-000",
    "classification": "confidential",
    "allowed_roles": ["security_engineer"],
    "department": "Engineering",
    "source_path": "confidential/DOC-009_incident.txt",
    "confidence": 0.98,
    "extraction_method": "regex:v1",
    "created_at": "2026-05-17T00:00:00Z"
}


def _make_context(user: dict | None, user_id: str, logs_dir: Path) -> AccessContext:
    return AccessContext(
        user=user,
        user_id=user_id,
        query='test query',
        top_k=10,
        logs_dir=logs_dir
    )


def test_secure_retrieve_filters_unauthorized(tmp_path: Path) -> None:
    ctx = _make_context(_EXTERNAL_VIEWER, 'external_viewer', tmp_path)
    result = secure_retrieve(ctx, _CANDIDATES)
    returned_ids = [record['chunk_id'] for record in result['results']]
    assert 'DOC-022-1' in returned_ids
    assert 'DOC-008-1' not in returned_ids


def test_secure_retrieve_security_engineer_sees_confidential(tmp_path: Path) -> None:
    ctx = _make_context(_SECURITY_ENGINEER, 'security_engineer', tmp_path)
    result = secure_retrieve(ctx, _CANDIDATES)
    returned_ids = [record['chunk_id'] for record in result['results']]
    assert 'DOC-008-1' in returned_ids


def test_secure_retrieve_strips_sensitive_fields(tmp_path: Path) -> None:
    ctx = _make_context(_EXTERNAL_VIEWER, 'external_viewer', tmp_path)
    result = secure_retrieve(ctx, _CANDIDATES)
    for record in result['results']:
        assert 'embedding_ciphertext' not in record
        assert 'embedding_nonce' not in record
        assert 'key_id' not in record


def test_secure_retrieve_unknown_user_denied(tmp_path: Path) -> None:
    ctx = AccessContext(
        user=None,
        user_id='ghost',
        query='test',
        top_k=5,
        logs_dir=tmp_path
    )
    result = secure_retrieve(ctx, _CANDIDATES)
    assert result['access_granted'] is False
    assert result['results'] == []


def test_secure_retrieve_writes_audit_log(tmp_path: Path) -> None:
    import json

    ctx = _make_context(_EXTERNAL_VIEWER, 'external_viewer', tmp_path)
    secure_retrieve(ctx, _CANDIDATES)
    audit_path = tmp_path / 'audit_log.jsonl'
    assert audit_path.exists()
    event = json.loads(audit_path.read_text(encoding='utf-8').splitlines()[0])
    assert event['event_type'] == 'search'
    assert event['mode'] == 'secure'


def test_insecure_retrieve_does_not_expose_unauthorized_content(tmp_path: Path) -> None:
    ctx = _make_context(_EXTERNAL_VIEWER, 'external_viewer', tmp_path)
    result = insecure_retrieve(ctx, _CANDIDATES)
    returned_ids = [record['chunk_id'] for record in result['results']]
    for blocked_id in result['filtered_out']:
        assert blocked_id not in returned_ids


def test_insecure_retrieve_strips_sensitive_fields(tmp_path: Path) -> None:
    ctx = _make_context(_EXTERNAL_VIEWER, 'external_viewer', tmp_path)
    result = insecure_retrieve(ctx, _CANDIDATES)
    for record in result['results']:
        assert 'embedding_ciphertext' not in record
        assert 'embedding_nonce' not in record
        assert 'key_id' not in record


def test_access_context_role_property() -> None:
    ctx = AccessContext(
        user={'role': 'admin'},
        user_id='admin',
        query='x',
        top_k=5,
        logs_dir=Path('logs')
    )
    assert ctx.role == 'admin'


def test_access_context_role_unknown_when_no_user() -> None:
    ctx = AccessContext(
        user=None,
        user_id='ghost',
        query='x',
        top_k=5,
        logs_dir=Path('logs')
    )
    assert ctx.role == 'unknown'


def test_admin_can_retrieve_confidential_fact(tmp_path: Path) -> None:
    ctx = AccessContext(
        user=_ADMIN,
        user_id="admin",
        query="Who was the Incident commander of PIPELINE OUTAGE 2024-01-15?",
        top_k=5,
        logs_dir=tmp_path
    )
    result = fact_retrieve(ctx, [_INCIDENT_FACT])
    assert result["answer"] == "The incident commander was hshaw@example.org."
    assert result["access_granted"] is True


def test_security_engineer_can_retrieve_confidential_fact(tmp_path: Path) -> None:
    ctx = AccessContext(
        user=_SECURITY_ENGINEER,
        user_id="security_engineer",
        query="Who was the Incident commander of PIPELINE OUTAGE 2024-01-15?",
        top_k=5,
        logs_dir=tmp_path
    )
    result = fact_retrieve(ctx, [_INCIDENT_FACT])
    assert result["answer"] == "The incident commander was hshaw@example.org."
    assert result["access_granted"] is True


def test_business_analyst_cannot_retrieve_confidential_fact(tmp_path: Path) -> None:
    ctx = AccessContext(
        user=_BUSINESS_ANALYST,
        user_id="business_analyst",
        query="Who was the Incident commander of PIPELINE OUTAGE 2024-01-15?",
        top_k=5,
        logs_dir=tmp_path
    )
    result = fact_retrieve(ctx, [_INCIDENT_FACT])
    assert result["answer"] == "No authorized information was found for your query."
    assert result["access_granted"] is False


def test_fact_query_returns_direct_answer_not_document_list(tmp_path: Path) -> None:
    ctx = AccessContext(
        user=_SECURITY_ENGINEER,
        user_id="security_engineer",
        query="Who was the Incident commander of PIPELINE OUTAGE 2024-01-15?",
        top_k=5,
        logs_dir=tmp_path
    )
    result = fact_retrieve(ctx, [_INCIDENT_FACT])
    assert result["handled"] is True
    assert result["facts"][0]["document_id"] == "DOC-009"
    assert result["answer"] == "The incident commander was hshaw@example.org."
    assert "results" not in result


def test_governance_fact_search_returns_fact_answer(tmp_path: Path) -> None:
    from secure_semantic_docs.governance.retrieval import fact_search

    users = {"security_engineer": _SECURITY_ENGINEER}
    result = fact_search(
        query="Who was the Incident commander of PIPELINE OUTAGE 2024-01-15?",
        user_id="security_engineer",
        facts=[_INCIDENT_FACT],
        users=users,
        logs_dir=tmp_path
    )
    assert result["answer"] == "The incident commander was hshaw@example.org."
    assert result["handled"] is True


# ---------------------------------------------------------------------------
# governed_retrieve — normalized result shape
# ---------------------------------------------------------------------------

def _make_governed_context(
    user: dict | None,
    user_id: str,
    query: str,
    logs_dir: Path
) -> AccessContext:
    return AccessContext(
        user=user,
        user_id=user_id,
        query=query,
        top_k=5,
        logs_dir=logs_dir
    )


_INCIDENT_QUERY = "Who was the Incident commander of PIPELINE OUTAGE 2024-01-15?"


def test_governed_retrieve_admin_returns_string_answer(tmp_path: Path) -> None:
    ctx = _make_governed_context(_ADMIN, "admin", _INCIDENT_QUERY, tmp_path)
    result = governed_retrieve(ctx, _CANDIDATES, [_INCIDENT_FACT])
    assert isinstance(result["answer"], str)


def test_governed_retrieve_admin_answer_equals_expected(tmp_path: Path) -> None:
    ctx = _make_governed_context(_ADMIN, "admin", _INCIDENT_QUERY, tmp_path)
    result = governed_retrieve(ctx, _CANDIDATES, [_INCIDENT_FACT])
    assert result["answer"] == "The incident commander was hshaw@example.org."


def test_governed_retrieve_security_engineer_answer_equals_expected(tmp_path: Path) -> None:
    ctx = _make_governed_context(
        _SECURITY_ENGINEER, "security_engineer", _INCIDENT_QUERY, tmp_path
    )
    result = governed_retrieve(ctx, _CANDIDATES, [_INCIDENT_FACT])
    assert result["answer"] == "The incident commander was hshaw@example.org."


def test_governed_retrieve_unauthorized_user_gets_no_authorized_info(tmp_path: Path) -> None:
    ctx = _make_governed_context(
        _BUSINESS_ANALYST, "business_analyst", _INCIDENT_QUERY, tmp_path
    )
    result = governed_retrieve(ctx, _CANDIDATES, [_INCIDENT_FACT])
    assert result["answer"] == "No authorized information was found for your query."
    assert result["status"] == "no_authorized_information"


def test_governed_retrieve_result_has_normalized_shape(tmp_path: Path) -> None:
    ctx = _make_governed_context(_ADMIN, "admin", _INCIDENT_QUERY, tmp_path)
    result = governed_retrieve(ctx, _CANDIDATES, [_INCIDENT_FACT])
    for key in ("answer", "answer_type", "status", "strategy", "sources",
                "blocked_count", "audit_request_id", "technical_details"):
        assert key in result, f"Missing key: {key}"


def test_governed_retrieve_fact_answer_type_is_fact_answer(tmp_path: Path) -> None:
    ctx = _make_governed_context(_ADMIN, "admin", _INCIDENT_QUERY, tmp_path)
    result = governed_retrieve(ctx, _CANDIDATES, [_INCIDENT_FACT])
    assert result["answer_type"] == "fact_answer"
    assert result["status"] == "answered"


def test_governed_retrieve_fact_query_does_not_return_generic_docs(tmp_path: Path) -> None:
    ctx = _make_governed_context(_ADMIN, "admin", _INCIDENT_QUERY, tmp_path)
    result = governed_retrieve(ctx, _CANDIDATES, [_INCIDENT_FACT])
    # The answer must be a plain string, not a list of document records
    assert isinstance(result["answer"], str)
    # Sources should not include the generic public chunks (DOC-022) for this fact query
    source_ids = [s.get("document_id") for s in result.get("sources", [])]
    assert "DOC-001" not in source_ids
    assert "DOC-002" not in source_ids
    assert "DOC-003" not in source_ids
    assert "DOC-004" not in source_ids
    assert "DOC-005" not in source_ids


def test_governed_retrieve_sources_contain_correct_document(tmp_path: Path) -> None:
    ctx = _make_governed_context(_ADMIN, "admin", _INCIDENT_QUERY, tmp_path)
    result = governed_retrieve(ctx, _CANDIDATES, [_INCIDENT_FACT])
    source_ids = [s.get("document_id") for s in result.get("sources", [])]
    assert "DOC-009" in source_ids


def test_governed_retrieve_technical_details_sanitized(tmp_path: Path) -> None:
    ctx = _make_governed_context(_ADMIN, "admin", _INCIDENT_QUERY, tmp_path)
    result = governed_retrieve(ctx, _CANDIDATES, [_INCIDENT_FACT])
    tech = result.get("technical_details", {})
    for forbidden in ("embedding_ciphertext", "embedding_nonce", "key_id",
                      "chunk_text_ciphertext", "chunk_text_nonce", "decrypted_embedding"):
        assert forbidden not in tech


def test_governed_retrieve_no_facts_no_candidates_returns_no_info(tmp_path: Path) -> None:
    ctx = _make_governed_context(_ADMIN, "admin", "General query about something", tmp_path)
    result = governed_retrieve(ctx, [], [])
    assert result["answer"] == "No authorized information was found for your query."
    assert result["status"] == "no_authorized_information"


def test_governed_retrieve_audit_request_id_is_string(tmp_path: Path) -> None:
    ctx = _make_governed_context(_ADMIN, "admin", _INCIDENT_QUERY, tmp_path)
    result = governed_retrieve(ctx, _CANDIDATES, [_INCIDENT_FACT])
    assert isinstance(result["audit_request_id"], str)
    assert len(result["audit_request_id"]) > 0


def test_governed_retrieve_fact_found_field_distinguished(tmp_path: Path) -> None:
    ctx = _make_governed_context(
        _BUSINESS_ANALYST, "business_analyst", _INCIDENT_QUERY, tmp_path
    )
    # Fact exists but business_analyst can't access it → fact_found=True
    raw = fact_retrieve(ctx, [_INCIDENT_FACT])
    assert raw.get("fact_found") is True
    assert raw.get("access_granted") is False


def test_governed_retrieve_no_matching_fact_sets_fact_found_false(tmp_path: Path) -> None:
    ctx = _make_governed_context(
        _ADMIN, "admin",
        "Who was the Incident commander of NON EXISTENT INCIDENT?",
        tmp_path
    )
    raw = fact_retrieve(ctx, [_INCIDENT_FACT])
    assert raw.get("fact_found") is False


def test_governed_search_wrapper_returns_normalized_shape(tmp_path: Path) -> None:
    from secure_semantic_docs.governance.retrieval import governed_search

    users = {"admin": _ADMIN}
    result = governed_search(
        query=_INCIDENT_QUERY,
        user_id="admin",
        candidates=_CANDIDATES,
        facts=[_INCIDENT_FACT],
        users=users,
        logs_dir=tmp_path
    )
    assert result["answer"] == "The incident commander was hshaw@example.org."
    assert result["status"] == "answered"
    assert result["answer_type"] == "fact_answer"
