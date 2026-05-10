"""Field-level encryption for document chunk dicts.

Only chunks with ``requires_encryption=True`` are modified; all other chunks
pass through unchanged.

Each encrypted field is replaced with its base64-encoded ciphertext and a
companion boolean flag ``{field}_is_encrypted`` is set to ``True``.
"""

from __future__ import annotations

from secure_semantic_docs.security.secretbox_encryptor import secretbox_encrypt_str


def encrypt_chunk_fields(
        chunk: dict[str, object],
        key: bytes,
        fields: list[str] | None = None
) -> dict[str, object]:
    """Return a copy of *chunk* with sensitive text fields encrypted.

    Only chunks with ``requires_encryption=True`` are modified; the rest are
    returned as shallow copies without touching any field values.

    Parameters
    ----------
    chunk:
        Chunk dictionary from the processing layer.
    key:
        32-byte secret key.
    fields:
        Field names to encrypt.  Defaults to ``["chunk_text"]``.

    Returns
    -------
    dict[str, object]
        Shallow copy of *chunk* with encrypted fields and flags applied.
    """
    if not chunk.get("requires_encryption", False):
        return dict(chunk)

    result = dict(chunk)
    for field_name in (fields or ["chunk_text"]):
        value = result.get(field_name)
        if isinstance(value, str):
            result[field_name] = secretbox_encrypt_str(value, key)
            result[f"{field_name}_is_encrypted"] = True

    return result
