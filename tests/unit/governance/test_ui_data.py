"""Tests for ui_data safe data helpers."""

from pathlib import Path
from typing import Any

import pytest

# noinspection PyProtectedMember
from secure_semantic_docs.governance.ui_data import (
    _sanitize_record,  # noqa: SLF001
    get_authorized_chunk_summary,
    get_audit_summary,
)


def _write_parquet(path: Path, records: list[dict]) -> None:
    """Write records as a Parquet file in the given directory."""
    import pandas as pd
    path.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(records)
    df.to_parquet(path / "part-00000.parquet", index=False)


@pytest.fixture
def bronze_dir(tmp_path: Path) -> Path:
    records = [
        {
            "document_id": "DOC-001",
            "title": "Public Guide",
            "classification": "public",
            "allowed_roles": [],
            "owner": "Alice",
            "department": "Data Platform",
            "version": "1.0",
            "source_path": "docs/public_guide.txt"
        },
        {
            "document_id": "DOC-008",
            "title": "Security Audit Report",
            "classification": "confidential",
            "allowed_roles": ["security_engineer"],
            "owner": "Bob",
            "department": "security",
            "version": "2.0",
            "source_path": "docs/security_audit.txt"
        }
    ]
    bronze_path = tmp_path / "bronze_documents"
    _write_parquet(bronze_path, records)
    return bronze_path


def test_authorized_chunk_summary_external_viewer_only_public(
    bronze_dir: Path, tmp_path: Path
):
    """External viewer should only see public documents."""
    user = {
        "user_id": "external_viewer",
        "role": "external_viewer",
        "department": "external",
        "clearance_level": "public"
    }
    silver_path = tmp_path / "silver_chunks"
    records = get_authorized_chunk_summary(user, bronze_dir, silver_path)

    assert all(r.get("classification") == "public" for r in records)
    assert not any(r.get("document_id") == "DOC-008" for r in records)


def test_authorized_chunk_summary_security_engineer_sees_confidential(
    bronze_dir: Path, tmp_path: Path
):
    """Security engineer should see confidential security documents."""
    user = {
        "user_id": "security_engineer",
        "role": "security_engineer",
        "department": "security",
        "clearance_level": "confidential"
    }
    silver_path = tmp_path / "silver_chunks"
    records = get_authorized_chunk_summary(user, bronze_dir, silver_path)

    doc_ids = [r.get("document_id") for r in records]
    assert "DOC-001" in doc_ids
    assert "DOC-008" in doc_ids


def test_authorized_chunk_summary_no_encrypted_fields(
    bronze_dir: Path, tmp_path: Path
):
    """Chunk summary must never include encrypted or forbidden fields."""
    user = {
        "user_id": "security_engineer",
        "role": "security_engineer",
        "department": "security",
        "clearance_level": "confidential"
    }
    silver_path = tmp_path / "silver_chunks"
    records = get_authorized_chunk_summary(user, bronze_dir, silver_path)

    for record in records:
        assert "embedding_ciphertext" not in record
        assert "embedding_nonce" not in record
        assert "key_id" not in record
        assert "chunk_text" not in record
        assert "raw_text" not in record


def test_sanitize_record_removes_forbidden_fields():
    """_sanitize_record must strip all forbidden fields and bytes values."""
    record: dict[str, Any] = {
        "document_id": "DOC-001",
        "title": "Test",
        "embedding_ciphertext": b"ciphertext",
        "embedding_nonce": b"nonce",
        "key_id": "key-001",
        "raw_text": "also sensitive",
        "document_hash": "abc123"
    }
    safe = _sanitize_record(record)
    assert "embedding_ciphertext" not in safe
    assert "embedding_nonce" not in safe
    assert "key_id" not in safe
    assert "raw_text" not in safe
    assert "document_hash" not in safe
    assert safe["document_id"] == "DOC-001"
    assert safe["title"] == "Test"


def test_get_audit_summary_non_admin_own_events_only(tmp_path: Path):
    """Non-admin user should only see their own audit events."""
    from secure_semantic_docs.governance.audit import log_search_event
    log_search_event(
        user_id="business_analyst",
        role="business_analyst",
        query="q1",
        mode="secure",
        returned_ids=[],
        filtered_out_ids=[],
        access_decisions={},
        decrypted_embedding_count=0,
        logs_dir=tmp_path
    )
    log_search_event(
        user_id="security_engineer",
        role="security_engineer",
        query="q2",
        mode="secure",
        returned_ids=[],
        filtered_out_ids=[],
        access_decisions={},
        decrypted_embedding_count=0,
        logs_dir=tmp_path
    )

    user = {"user_id": "business_analyst", "role": "business_analyst"}
    events = get_audit_summary(user, logs_dir=tmp_path)
    assert all(e["user_id"] == "business_analyst" for e in events)
    assert len(events) == 1


def test_authorized_chunk_summary_empty_if_no_parquet(tmp_path: Path):
    """Returns empty list when lakehouse has no data."""
    user = {"user_id": "admin", "role": "admin", "clearance_level": "restricted"}
    records = get_authorized_chunk_summary(
        user, tmp_path / "bronze", tmp_path / "silver"
    )
    assert records == []
