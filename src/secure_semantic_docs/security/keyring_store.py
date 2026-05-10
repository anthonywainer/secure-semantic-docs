"""Secret key generation and OS-keyring-based key material loading.

Resolution order
----------------
1. ``DOCSEC_SECRET_KEY`` environment variable — base64-encoded 32-byte key.
   ``key_id`` is the sentinel ``"env-key"``.
2. OS credential store via the ``keyring`` library (macOS Keychain, Windows
   Credential Manager, Linux Secret Service / KWallet).  Service name:
   ``"secure-semantic-docs"``, entries: ``"embedding-key"`` and
   ``"embedding-key-id"``.
3. A freshly generated key + UUID written to the OS keyring on first run.

The ``key_id`` UUID is stored alongside every encrypted record.  It is safe
to log; it identifies which key encrypted a record without revealing the key
itself, enabling future key rotation without an immediate full re-encrypt.

Production
----------
Inject the key via the ``DOCSEC_SECRET_KEY`` environment variable and manage
rotation through a dedicated KMS (AWS KMS, HashiCorp Vault, etc.).
"""

from __future__ import annotations

import base64
import logging
import os
import uuid

import keyring
import nacl.secret
import nacl.utils

from secure_semantic_docs.core import BaseSettings
from secure_semantic_docs.core.exceptions import EncryptionError
from secure_semantic_docs.loader import load_config
from secure_semantic_docs.models import Config

logger = logging.getLogger(BaseSettings.APP_NAME)

KEYRING_SERVICE = "secure-semantic-docs"
SECRET_KEY_CREDENTIAL = "embedding-key"
KEY_VERSION_CREDENTIAL = "embedding-key-id"

_KEY_SIZE = nacl.secret.SecretBox.KEY_SIZE


def generate_secret_key() -> bytes:
    """Generate a new random 32-byte secret key."""
    return nacl.utils.random(_KEY_SIZE)


def resolve_secret_key(config: Config | None = None) -> bytes:
    """Return the active secret key bytes.

    Thin wrapper around :func:`resolve_key_material` for callers that
    do not need the ``key_id``.
    """
    key, _key_id = resolve_key_material(config)
    return key


def resolve_key_material(config: Config | None = None) -> tuple[bytes, str]:
    """Return ``(key_bytes, key_id)`` for the active secret key.

    See the module docstring for the resolution order.

    Parameters
    ----------
    config:
        Project configuration.  Loaded from YAML if *None*.

    Returns
    -------
    tuple[bytes, str]
        ``(32-byte key, key_id string)``.

    Raises
    ------
    EncryptionError
        When the env-var key cannot be decoded or has the wrong length.
    """
    cfg = config or load_config()
    return (
            _load_from_env(cfg.secret_key_env_var)
            or _load_from_keyring()
            or _generate_and_store()
    )


def _decode_and_validate_key(b64_value: str, source: str) -> bytes:
    """Decode a base64 key string and validate its length.

    Raises :exc:`EncryptionError` when decoding fails or length is wrong.
    """
    try:
        key = base64.b64decode(b64_value)
    except Exception as exc:
        raise EncryptionError(f"Failed to decode key from {source}: {exc}") from exc
    if len(key) != _KEY_SIZE:
        raise EncryptionError(
            f"Key from {source} must be {_KEY_SIZE} bytes after base64 decoding."
        )
    return key


def _load_from_env(env_var: str) -> tuple[bytes, str] | None:
    """Return key material from the environment variable, or *None* if unset."""
    raw = os.environ.get(env_var)
    if not raw:
        return None
    key = _decode_and_validate_key(raw, env_var)
    logger.debug("Loaded secret key from environment variable.")
    return key, "env-key"


def _load_from_keyring() -> tuple[bytes, str] | None:
    """Return key material from the OS keyring, or *None* if not stored."""
    stored_b64 = keyring.get_password(KEYRING_SERVICE, SECRET_KEY_CREDENTIAL)
    if stored_b64 is None:
        return None
    key = _decode_and_validate_key(stored_b64, "OS keyring")
    key_id = keyring.get_password(KEYRING_SERVICE, KEY_VERSION_CREDENTIAL) or "unknown"
    logger.debug("Loaded local dev key from OS keyring (key_id=%s)", key_id)
    return key, key_id


def _generate_and_store() -> tuple[bytes, str]:
    """Generate a new key, persist it in the OS keyring, and return it."""
    key = generate_secret_key()
    key_id = str(uuid.uuid4())
    keyring.set_password(
        KEYRING_SERVICE,
        SECRET_KEY_CREDENTIAL,
        base64.b64encode(key).decode("ascii")
    )
    keyring.set_password(KEYRING_SERVICE, KEY_VERSION_CREDENTIAL, key_id)
    logger.info("Generated and stored local dev key in OS keyring (key_id=%s)", key_id)
    return key, key_id
