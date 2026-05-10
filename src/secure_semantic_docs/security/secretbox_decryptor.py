"""XSalsa20-Poly1305 authenticated decryption via PyNaCl SecretBox."""

from __future__ import annotations

import base64

import nacl.secret

from secure_semantic_docs.core.exceptions import EncryptionError


def secretbox_decrypt(ciphertext: bytes, nonce: bytes, key: bytes) -> bytes:
    """Decrypt bytes produced by ``secretbox_encrypt``."""
    try:
        box = nacl.secret.SecretBox(key)
        return bytes(box.decrypt(ciphertext, nonce=nonce))
    except Exception as exc:
        raise EncryptionError(f"Byte decryption failed: {exc}") from exc


def secretbox_decrypt_str(ciphertext_b64: str, key: bytes) -> str:
    """Decrypt a string produced by ``secretbox_encrypt_str``."""
    try:
        box = nacl.secret.SecretBox(key)
        raw = base64.b64decode(ciphertext_b64)
        return box.decrypt(raw).decode("utf-8")
    except Exception as exc:
        raise EncryptionError(f"String decryption failed: {exc}") from exc
