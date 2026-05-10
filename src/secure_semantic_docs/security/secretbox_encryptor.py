"""XSalsa20-Poly1305 authenticated encryption via PyNaCl SecretBox.

Nonces are generated randomly per call — encrypting the same plaintext twice
always produces a different ciphertext, preventing nonce-reuse attacks.

:func:`secretbox_encrypt`
    Raw byte encryption.  Nonce and ciphertext are returned as separate
    ``bytes`` objects so they can be stored in distinct gold schema columns.
    Used for embedding vectors.

:func:`secretbox_encrypt_str`
    String convenience wrapper.  Nonce is prepended to the ciphertext and the
    whole payload is base64-encoded as a single string.  Used for sensitive
    document fields.
"""

from __future__ import annotations

import base64

import nacl.secret

from secure_semantic_docs.core.exceptions import EncryptionError

EMBEDDING_ENCRYPTION_ALGORITHM: str = "XSalsa20-Poly1305"
"""Algorithm label stored in the gold schema alongside every encrypted embedding.

Recording the algorithm identifier enables future migration to a different
cipher without losing the ability to decrypt older rows.
"""


def secretbox_encrypt(plaintext_bytes: bytes, key: bytes) -> tuple[bytes, bytes]:
    """Encrypt raw bytes and return ``(ciphertext, nonce)`` separately.

    Parameters
    ----------
    plaintext_bytes:
        The raw bytes to encrypt (e.g. a serialised embedding vector).
    key:
        32-byte secret key.

    Returns
    -------
    tuple[bytes, bytes]
        ``(ciphertext, nonce)`` — both are required for decryption.
        The 24-byte nonce is randomly generated per call.

    Raises
    ------
    EncryptionError
        On any underlying cryptographic failure.
    """
    try:
        box = nacl.secret.SecretBox(key)
        encrypted = box.encrypt(plaintext_bytes)
        return bytes(encrypted.ciphertext), bytes(encrypted.nonce)
    except Exception as exc:
        raise EncryptionError(f"Byte encryption failed: {exc}") from exc


def secretbox_encrypt_str(plaintext: str, key: bytes) -> str:
    """Encrypt a UTF-8 string and return a single base64-encoded payload.

    The nonce is prepended to the ciphertext before base64 encoding so the
    result is self-contained — no separate nonce column is needed.

    Parameters
    ----------
    plaintext:
        The string value to encrypt.
    key:
        32-byte secret key.

    Returns
    -------
    str
        Base64-encoded ``nonce || ciphertext``.

    Raises
    ------
    EncryptionError
        On any underlying cryptographic failure.
    """
    try:
        box = nacl.secret.SecretBox(key)
        encrypted = box.encrypt(plaintext.encode("utf-8"))
        return base64.b64encode(bytes(encrypted)).decode("ascii")
    except Exception as exc:
        raise EncryptionError(f"String encryption failed: {exc}") from exc
