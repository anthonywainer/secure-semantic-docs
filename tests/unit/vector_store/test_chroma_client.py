"""Tests for Chroma vector index client."""

from typing import Any

import pytest

# noinspection PyProtectedMember
from secure_semantic_docs.vector_store.chroma_client import (
    ChromaConfig,
    _FORBIDDEN_PAYLOAD_FIELDS,  # noqa: SLF001
    _SAFE_METADATA_FIELDS,  # noqa: SLF001
    build_safe_metadata
)


@pytest.fixture
def gold_record() -> dict[str, Any]:
    return {
        'chunk_id': 'DOC-001-1',
        'document_id': 'DOC-001',
        'classification': 'internal',
        'allowed_roles': ['business_analyst', 'data_engineer'],
        'department': 'Operations',
        'owner': 'Alice',
        'version': '1.0',
        'sensitivity_level': 'medium',
        'embedding_ciphertext': b'fakeciphertext',
        'embedding_nonce': b'fakenonce',
        'key_id': 'key-001',
        'chunk_text': 'This is secret text',
        'raw_text': 'Raw content here'
    }



def test_build_safe_metadata_excludes_forbidden(gold_record: dict[str, Any]) -> None:
    metadata = build_safe_metadata(gold_record)
    for forbidden_name in _FORBIDDEN_PAYLOAD_FIELDS:
        assert forbidden_name not in metadata



def test_build_safe_metadata_excludes_bytes(gold_record: dict[str, Any]) -> None:
    metadata = build_safe_metadata(gold_record)
    for value in metadata.values():
        assert not isinstance(value, (bytes, bytearray))



def test_build_safe_metadata_includes_safe_fields(gold_record: dict[str, Any]) -> None:
    metadata = build_safe_metadata(gold_record)
    assert metadata.get('chunk_id') == 'DOC-001-1'
    assert metadata.get('document_id') == 'DOC-001'
    assert metadata.get('classification') == 'internal'



def test_build_safe_metadata_converts_list_to_string(gold_record: dict[str, Any]) -> None:
    metadata = build_safe_metadata(gold_record)
    roles = metadata.get('allowed_roles')
    assert isinstance(roles, str)
    assert 'business_analyst' in roles



def test_build_safe_metadata_empty_record() -> None:
    metadata = build_safe_metadata({})
    assert isinstance(metadata, dict)
    assert len(metadata) == 0



def test_chroma_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('CHROMA_HOST', raising=False)
    monkeypatch.delenv('CHROMA_PORT', raising=False)
    config = ChromaConfig()
    assert config.host == 'localhost'
    assert config.port == 8000



def test_chroma_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('CHROMA_HOST', 'chroma-server')
    monkeypatch.setenv('CHROMA_PORT', '9000')
    config = ChromaConfig()
    assert config.host == 'chroma-server'
    assert config.port == 9000



def test_forbidden_fields_set_contains_sensitive() -> None:
    assert 'embedding_ciphertext' in _FORBIDDEN_PAYLOAD_FIELDS
    assert 'embedding_nonce' in _FORBIDDEN_PAYLOAD_FIELDS
    assert 'key_id' in _FORBIDDEN_PAYLOAD_FIELDS
    assert 'chunk_text' in _FORBIDDEN_PAYLOAD_FIELDS
    assert 'raw_text' in _FORBIDDEN_PAYLOAD_FIELDS



def test_safe_metadata_fields_does_not_include_forbidden() -> None:
    for field_name in _FORBIDDEN_PAYLOAD_FIELDS:
        assert field_name not in _SAFE_METADATA_FIELDS
