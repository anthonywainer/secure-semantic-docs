"""Unit tests for secretbox encryption helpers and key material loading."""

import base64
import uuid

import pytest

from secure_semantic_docs.core.exceptions import EncryptionError
from secure_semantic_docs.security.keyring_store import (
    KEYRING_SERVICE,
    KEY_VERSION_CREDENTIAL,
    SECRET_KEY_CREDENTIAL,
    generate_secret_key,
    resolve_key_material
)
from secure_semantic_docs.security.secretbox_decryptor import secretbox_decrypt
from secure_semantic_docs.security.secretbox_encryptor import (
    EMBEDDING_ENCRYPTION_ALGORITHM,
    secretbox_encrypt
)


class TestEncryptBytes:
    def test_returns_bytes_tuple(self):
        key = generate_secret_key()
        ciphertext, nonce = secretbox_encrypt(b'hello', key)
        assert isinstance(ciphertext, bytes)
        assert isinstance(nonce, bytes)

    def test_nonce_is_24_bytes(self):
        key = generate_secret_key()
        _, nonce = secretbox_encrypt(b'hello', key)
        assert len(nonce) == 24

    def test_different_calls_produce_different_nonces(self):
        key = generate_secret_key()
        _, nonce1 = secretbox_encrypt(b'same', key)
        _, nonce2 = secretbox_encrypt(b'same', key)
        assert nonce1 != nonce2

    def test_ciphertext_differs_from_plaintext(self):
        key = generate_secret_key()
        plaintext = b'secret vector bytes'
        ciphertext, _ = secretbox_encrypt(plaintext, key)
        assert ciphertext != plaintext

    def test_bad_key_raises_encryption_error(self):
        with pytest.raises(EncryptionError):
            secretbox_encrypt(b'data', b'tooshort')


class TestDecryptBytes:
    def test_round_trip(self):
        key = generate_secret_key()
        plaintext = b'\x00\x01\x02\x03' * 96
        ciphertext, nonce = secretbox_encrypt(plaintext, key)
        recovered = secretbox_decrypt(ciphertext, nonce, key)
        assert recovered == plaintext

    def test_wrong_key_raises_encryption_error(self):
        key1 = generate_secret_key()
        key2 = generate_secret_key()
        ciphertext, nonce = secretbox_encrypt(b'secret', key1)
        with pytest.raises(EncryptionError):
            secretbox_decrypt(ciphertext, nonce, key2)

    def test_tampered_ciphertext_raises_encryption_error(self):
        key = generate_secret_key()
        ciphertext, nonce = secretbox_encrypt(b'secret', key)
        tampered = bytes([ciphertext[0] ^ 0xFF]) + ciphertext[1:]
        with pytest.raises(EncryptionError):
            secretbox_decrypt(tampered, nonce, key)

    def test_empty_plaintext_round_trip(self):
        key = generate_secret_key()
        ciphertext, nonce = secretbox_encrypt(b'', key)
        assert secretbox_decrypt(ciphertext, nonce, key) == b''


class TestAlgorithmConstant:
    def test_value(self):
        assert EMBEDDING_ENCRYPTION_ALGORITHM == 'XSalsa20-Poly1305'


class TestResolveKeyMaterial:
    def test_generates_and_stores_key_on_first_call(self, tmp_path, monkeypatch):
        from secure_semantic_docs.models import Config
        monkeypatch.setenv('DOCSEC_SECRET_KEY', '')
        cfg = Config(project_root=tmp_path)

        keyring_store: dict[tuple[str, str], str] = {}

        def mock_get(service: str, username: str) -> str | None:
            return keyring_store.get((service, username))

        def mock_set(service: str, username: str, value: str) -> None:
            keyring_store[(service, username)] = value

        monkeypatch.setattr('secure_semantic_docs.security.keyring_store.keyring.get_password', mock_get)
        monkeypatch.setattr('secure_semantic_docs.security.keyring_store.keyring.set_password', mock_set)

        key, key_id = resolve_key_material(cfg)

        assert len(key) == 32
        assert len(str(uuid.UUID(key_id))) == 36
        assert keyring_store[(KEYRING_SERVICE, SECRET_KEY_CREDENTIAL)] is not None
        assert keyring_store[(KEYRING_SERVICE, KEY_VERSION_CREDENTIAL)] == key_id

    def test_reads_existing_key_from_keyring(self, tmp_path, monkeypatch):
        from secure_semantic_docs.models import Config
        monkeypatch.setenv('DOCSEC_SECRET_KEY', '')
        cfg = Config(project_root=tmp_path)

        expected_key = generate_secret_key()
        expected_key_id = str(uuid.uuid4())
        keyring_store = {
            (KEYRING_SERVICE, SECRET_KEY_CREDENTIAL): base64.b64encode(expected_key).decode('ascii'),
            (KEYRING_SERVICE, KEY_VERSION_CREDENTIAL): expected_key_id
        }

        monkeypatch.setattr(
            'secure_semantic_docs.security.keyring_store.keyring.get_password',
            lambda s, u: keyring_store.get((s, u))
        )

        key, key_id = resolve_key_material(cfg)
        assert key == expected_key
        assert key_id == expected_key_id

    def test_env_var_returns_env_key_id(self, tmp_path, monkeypatch):
        from secure_semantic_docs.models import Config
        raw_key = generate_secret_key()
        monkeypatch.setenv('DOCSEC_SECRET_KEY', base64.b64encode(raw_key).decode('ascii'))
        cfg = Config(project_root=tmp_path)

        key, key_id = resolve_key_material(cfg)
        assert key == raw_key
        assert key_id == 'env-key'

    def test_second_call_reuses_same_key(self, tmp_path, monkeypatch):
        from secure_semantic_docs.models import Config
        monkeypatch.setenv('DOCSEC_SECRET_KEY', '')
        cfg = Config(project_root=tmp_path)

        keyring_store: dict[tuple[str, str], str] = {}

        def mock_get(service: str, username: str) -> str | None:
            return keyring_store.get((service, username))

        def mock_set(service: str, username: str, value: str) -> None:
            keyring_store[(service, username)] = value

        monkeypatch.setattr('secure_semantic_docs.security.keyring_store.keyring.get_password', mock_get)
        monkeypatch.setattr('secure_semantic_docs.security.keyring_store.keyring.set_password', mock_set)

        key1, kid1 = resolve_key_material(cfg)
        key2, kid2 = resolve_key_material(cfg)
        assert key1 == key2
        assert kid1 == kid2


class TestResolveSecretKey:
    def test_returns_key_bytes(self, tmp_path, monkeypatch):
        from secure_semantic_docs.models import Config
        from secure_semantic_docs.security.keyring_store import resolve_secret_key
        raw_key = generate_secret_key()
        monkeypatch.setenv('DOCSEC_SECRET_KEY', base64.b64encode(raw_key).decode('ascii'))
        cfg = Config(project_root=tmp_path)
        assert resolve_secret_key(cfg) == raw_key


class TestDecodeAndValidateKey:
    def test_invalid_base64_raises_via_env(self, tmp_path, monkeypatch):
        from secure_semantic_docs.models import Config
        monkeypatch.setenv('DOCSEC_SECRET_KEY', '!!!not-base64!!!')
        cfg = Config(project_root=tmp_path)
        with pytest.raises(EncryptionError, match="Failed to decode key"):
            resolve_key_material(cfg)

    def test_wrong_key_length_raises_via_env(self, tmp_path, monkeypatch):
        from secure_semantic_docs.models import Config
        short_key = base64.b64encode(b'tooshort').decode('ascii')
        monkeypatch.setenv('DOCSEC_SECRET_KEY', short_key)
        cfg = Config(project_root=tmp_path)
        with pytest.raises(EncryptionError, match="must be 32 bytes"):
            resolve_key_material(cfg)


class TestEncryptStr:
    def test_round_trip(self):
        from secure_semantic_docs.security.secretbox_decryptor import secretbox_decrypt_str
        from secure_semantic_docs.security.secretbox_encryptor import secretbox_encrypt_str
        key = generate_secret_key()
        ciphertext = secretbox_encrypt_str("hello", key)
        assert secretbox_decrypt_str(ciphertext, key) == "hello"

    def test_decrypt_bad_payload_raises_encryption_error(self):
        from secure_semantic_docs.security.secretbox_decryptor import secretbox_decrypt_str
        key = generate_secret_key()
        with pytest.raises(EncryptionError, match="String decryption failed"):
            secretbox_decrypt_str("not-base64", key)

    def test_bad_key_raises_encryption_error(self):
        from secure_semantic_docs.security.secretbox_encryptor import secretbox_encrypt_str
        with pytest.raises(EncryptionError):
            secretbox_encrypt_str("hello", b"tooshort")


class TestEncryptChunkFields:
    def test_encrypts_when_required(self):
        from secure_semantic_docs.security.chunk_field_encryptor import encrypt_chunk_fields
        key = generate_secret_key()
        chunk = {"chunk_text": "sensitive data", "requires_encryption": True}
        result = encrypt_chunk_fields(chunk, key)
        assert result["chunk_text"] != "sensitive data"
        assert result["chunk_text_is_encrypted"] is True

    def test_skips_non_string_field(self):
        from secure_semantic_docs.security.chunk_field_encryptor import encrypt_chunk_fields
        key = generate_secret_key()
        chunk = {"chunk_text": None, "requires_encryption": True}
        result = encrypt_chunk_fields(chunk, key)
        assert result.get("chunk_text_is_encrypted") is None

    def test_passthrough_when_not_required(self):
        from secure_semantic_docs.security.chunk_field_encryptor import encrypt_chunk_fields
        key = generate_secret_key()
        chunk = {"chunk_text": "plain", "requires_encryption": False}
        result = encrypt_chunk_fields(chunk, key)
        assert result["chunk_text"] == "plain"
