"""Tests for result_sanitizer module."""

# noinspection PyProtectedMember
from secure_semantic_docs.serving.result_sanitizer import (
    _DEFAULT_GOLD_FORBIDDEN,  # noqa: SLF001
    sanitize_record,
    sanitize_result
)

_DEFAULT_FORBIDDEN = _DEFAULT_GOLD_FORBIDDEN


def test_sanitize_removes_default_forbidden_fields() -> None:
    record = {
        "chunk_id": "DOC-001-1",
        "classification": "public",
        "embedding_ciphertext": b"abc",
        "embedding_nonce": b"nonce",
        "key_id": "key-001",
        "title": "Test"
    }
    result = sanitize_result(record)
    assert "embedding_ciphertext" not in result
    assert "embedding_nonce" not in result
    assert "key_id" not in result
    assert result["chunk_id"] == "DOC-001-1"
    assert result["title"] == "Test"


def test_sanitize_with_custom_forbidden() -> None:
    record = {"a": 1, "b": 2, "c": 3}
    result = sanitize_result(record, forbidden_fields=frozenset({"b"}))
    assert "b" not in result
    assert result["a"] == 1
    assert result["c"] == 3


def test_sanitize_empty_record() -> None:
    assert sanitize_result({}) == {}


def test_sanitize_no_forbidden_fields_present() -> None:
    record = {"chunk_id": "x", "title": "y"}
    result = sanitize_result(record)
    assert result == {"chunk_id": "x", "title": "y"}


def test_default_gold_forbidden_contains_sensitive_fields() -> None:
    assert "embedding_ciphertext" in _DEFAULT_GOLD_FORBIDDEN
    assert "embedding_nonce" in _DEFAULT_GOLD_FORBIDDEN
    assert "key_id" in _DEFAULT_GOLD_FORBIDDEN


# ---------------------------------------------------------------------------
# sanitize_record — UI-safe sanitization
# ---------------------------------------------------------------------------

def test_sanitize_record_removes_embedding_fields() -> None:
    record = {
        "chunk_id": "c1",
        "embedding_ciphertext": b"cipher",
        "embedding_nonce": b"nonce",
        "key_id": "k1"
    }
    result = sanitize_record(record)
    assert "embedding_ciphertext" not in result
    assert "embedding_nonce" not in result
    assert "key_id" not in result
    assert result["chunk_id"] == "c1"


def test_sanitize_record_removes_extended_ui_forbidden_fields() -> None:
    record = {
        "chunk_id": "c1",
        "chunk_text_ciphertext": b"x",
        "chunk_text_nonce": b"y",
        "decrypted_embedding": [0.1, 0.2],
        "raw_text": "secret content",
        "encrypted_text": "cipher",
        "password": "hunter2",
        "secret": "topsecret",
        "document_hash": "abc123"
    }
    result = sanitize_record(record)
    for forbidden in (
        "chunk_text_ciphertext", "chunk_text_nonce", "decrypted_embedding",
        "raw_text", "encrypted_text", "password", "secret", "document_hash"
    ):
        assert forbidden not in result
    assert result["chunk_id"] == "c1"


def test_sanitize_record_strips_bytes_values() -> None:
    record = {"chunk_id": "c1", "some_bytes": b"raw bytes", "title": "ok"}
    result = sanitize_record(record)
    assert "some_bytes" not in result
    assert result["title"] == "ok"


def test_sanitize_record_preserves_safe_fields() -> None:
    record = {
        "document_id": "DOC-009",
        "chunk_id": "DOC-009-000",
        "classification": "confidential",
        "score": 0.95,
        "source_path": "confidential/DOC-009_incident.txt"
    }
    result = sanitize_record(record)
    assert result == record


def test_sanitize_record_empty_input() -> None:
    assert sanitize_record({}) == {}
