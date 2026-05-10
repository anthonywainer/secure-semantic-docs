"""Unit tests for the encrypted vector store."""

import pytest

from secure_semantic_docs.embeddings.serializer import embedding_to_bytes
from secure_semantic_docs.security.keyring_store import generate_secret_key
from secure_semantic_docs.security.secretbox_encryptor import secretbox_encrypt


def _make_gold_row(
        chunk_id: str,
        vector: list[float],
        key: bytes,
        allowed_roles: list[str],
        classification: str = 'internal',
        owner: str = 'alice',
        department: str = 'eng'
) -> dict:
    """Build a synthetic gold row dict with an encrypted embedding."""
    raw = embedding_to_bytes(vector)
    ciphertext, nonce = secretbox_encrypt(raw, key)
    return {
        'embedding_id': f'emb-{chunk_id}',
        'chunk_id': chunk_id,
        'document_id': 'doc-1',
        'embedding_ciphertext': ciphertext,
        'embedding_nonce': nonce,
        'embedding_algorithm': 'XSalsa20-Poly1305',
        'embedding_dim': len(vector),
        'embedding_dtype': 'float32',
        'embedding_model': 'test-model',
        'key_id': 'test-key-id',
        'classification': classification,
        'allowed_roles': allowed_roles,
        'owner': owner,
        'department': department,
        'source_path': '/docs/test.txt',
        'version': '1',
        'document_hash': 'abc123',
        'created_at': '2024-01-01T00:00:00Z'
    }


@pytest.fixture
def encryption_key() -> bytes:
    return generate_secret_key()


@pytest.fixture
def encrypted_rows(encryption_key):
    """Four rows: two for analysts, one for security, one for all."""
    return [
        _make_gold_row('c1', [1.0, 0.0, 0.0, 0.0], encryption_key, ['reader', 'analyst'], 'internal'),
        _make_gold_row('c2', [0.9, 0.1, 0.0, 0.0], encryption_key, ['reader', 'analyst'], 'internal'),
        _make_gold_row('c3', [0.0, 0.0, 1.0, 0.0], encryption_key, ['security'], 'confidential'),
        _make_gold_row('c4', [0.5, 0.5, 0.0, 0.0], encryption_key, ['reader'], 'public')
    ]
