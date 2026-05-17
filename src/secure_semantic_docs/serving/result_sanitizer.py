"""Result sanitization: removes sensitive fields before returning to callers."""

import logging
from pathlib import Path

from secure_semantic_docs.core.settings import BaseSettings
from secure_semantic_docs.governance.contracts import get_sensitive_fields

logger = logging.getLogger(BaseSettings.APP_NAME)

_DEFAULT_GOLD_FORBIDDEN: frozenset[str] = frozenset({
    "embedding_ciphertext",
    "embedding_nonce",
    "key_id"
})

_ALWAYS_FORBIDDEN: frozenset[str] = _DEFAULT_GOLD_FORBIDDEN

_UI_EXTRA_FORBIDDEN: frozenset[str] = frozenset({
    "chunk_text_ciphertext",
    "chunk_text_nonce",
    "decrypted_embedding",
    "raw_text",
    "document_hash",
    "encrypted_text",
    "secret",
    "password",
})

_UI_FORBIDDEN_FIELDS: frozenset[str] = _ALWAYS_FORBIDDEN | _UI_EXTRA_FORBIDDEN


def get_gold_forbidden_fields(contracts_dir: Path | str | None = None) -> frozenset[str]:
    """Return the set of forbidden fields for gold_embeddings from contracts.

    Falls back to the default set if contracts are unavailable.

    Parameters
    ----------
    contracts_dir
        Override for contracts directory.
    """
    try:
        fields = get_sensitive_fields("gold_embeddings", contracts_dir)
        return frozenset(fields) if fields else _DEFAULT_GOLD_FORBIDDEN
    except Exception as exc:
        logger.debug("Could not load gold forbidden fields from contracts: %s", exc)
        return _DEFAULT_GOLD_FORBIDDEN


def sanitize_result(
        record: dict,
        forbidden_fields: frozenset[str] | None = None
) -> dict:
    """Strip sensitive fields from a record before returning to callers.

    Removes gold embedding encryption internals by default.

    Parameters
    ----------
    record
        Raw record dict (may contain sensitive fields).
    forbidden_fields
        Fields to remove. Defaults to contract-derived forbidden fields
        from gold_embeddings.

    Returns
    -------
    dict
        Record with sensitive fields removed.
    """
    effective_forbidden = (
        forbidden_fields
        if forbidden_fields is not None
        else get_gold_forbidden_fields()
    )
    return {
        key: value
        for key, value in record.items()
        if key not in effective_forbidden
    }


def sanitize_record(record: dict) -> dict:
    """Strip all fields unsafe for UI display.

    Applies the complete set of UI-forbidden fields (encryption internals,
    raw text, secrets, passwords) and removes any bytes/bytearray values
    that cannot be safely serialized.

    Parameters
    ----------
    record
        Arbitrary record dict that may contain sensitive or non-serializable
        fields.

    Returns
    -------
    dict
        Record safe for display in the Streamlit UI or JSON expanders.
    """
    return {
        key: value
        for key, value in record.items()
        if key not in _UI_FORBIDDEN_FIELDS and not isinstance(value, (bytes, bytearray))
    }
