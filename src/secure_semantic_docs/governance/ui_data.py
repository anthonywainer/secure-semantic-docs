"""Safe data access helpers for the Streamlit UI.

All functions return sanitized records only.
Sensitive fields (embedding_ciphertext, embedding_nonce, key_id, raw embeddings)
are never included in the output.
"""

import logging
from pathlib import Path
from typing import Any

from secure_semantic_docs.core.settings import BaseSettings
from secure_semantic_docs.governance.audit import get_audit_summary_for_ui
from secure_semantic_docs.governance.catalog import generate_openmetadata_assets
from secure_semantic_docs.governance.permissions import can_access_record

logger = logging.getLogger(BaseSettings.APP_NAME)

_CHUNK_SUMMARY_FIELDS = frozenset({
    "document_id",
    "chunk_id",
    "title",
    "classification",
    "owner",
    "department",
    "version",
    "source_path",
})

_BRONZE_SUMMARY_FIELDS = frozenset({
    "document_id",
    "title",
    "classification",
    "owner",
    "department",
    "version",
    "source_path",
    "allowed_roles",
})

_FORBIDDEN_FIELDS = frozenset({
    "embedding_ciphertext",
    "embedding_nonce",
    "key_id",
    "raw_text",
    "document_hash",
})


def _load_parquet_records(layer_path: Path) -> list[dict]:
    """Load Parquet records from a directory. Returns empty list on failure."""
    if not layer_path.exists():
        return []
    try:
        import pandas as pd
        parquet_files = list(layer_path.rglob("*.parquet"))
        if not parquet_files:
            return []
        df = pd.concat([pd.read_parquet(f) for f in parquet_files], ignore_index=True)
        return df.to_dict("records")
    except Exception as exc:
        logger.warning("Could not load Parquet from %s: %s", layer_path, exc)
        return []


def _pick_fields(record: dict, allowed: frozenset[str]) -> dict:
    """Return a new dict with only allowed fields."""
    return {k: v for k, v in record.items() if k in allowed}


def _sanitize_record(record: dict) -> dict:
    """Remove forbidden fields and convert non-JSON-safe types."""
    result = {}
    for k, v in record.items():
        if k in _FORBIDDEN_FIELDS:
            continue
        if isinstance(v, (bytes, bytearray, memoryview)):
            continue
        if isinstance(v, list):
            result[k] = [str(i) if not isinstance(i, str) else i for i in v]
        else:
            result[k] = v
    return result


def get_authorized_chunk_summary(
        user: dict,
        bronze_path: Path | str,
        _silver_path: Path | str | None = None
) -> list[dict]:
    """Return a sanitized summary of documents/chunks the user is authorized to see.

    Parameters
    ----------
    user
        Authenticated user record.
    bronze_path
        Path to bronze_documents Parquet directory.
    _silver_path
        Optional path to silver_chunks Parquet directory for richer metadata.

    Returns
    -------
    list[dict]
        Sanitized records with safe fields only. No raw text, no encrypted fields.
    """
    bronze_records = _load_parquet_records(Path(bronze_path))
    authorized = []

    for record in bronze_records:
        if not can_access_record(user, record):
            continue
        safe = _sanitize_record(record)
        summary = _pick_fields(safe, _BRONZE_SUMMARY_FIELDS)
        summary["access_status"] = "authorized"
        authorized.append(summary)

    return authorized


def get_governance_summary(
        _user: dict,
        project_root: Path | str = "."
) -> list[dict]:
    """Return governance/catalog summary safe for display in the UI.

    Parameters
    ----------
    _user
        Authenticated user record (reserved for future role-based filtering).
    project_root
        Project root directory for catalog generation.

    Returns
    -------
    list[dict]
        Governance entities with safe fields only.
    """
    catalog = generate_openmetadata_assets(project_root)
    entities = catalog.get("entities", [])

    safe_entities: list[dict[str, Any]] = []
    for entity in entities:
        safe_entities.append({
            "id": entity.get("id", ""),
            "name": entity.get("name", ""),
            "type": entity.get("type", ""),
            "owner": entity.get("owner", ""),
            "description": entity.get("description", ""),
            "tags": entity.get("tags", []),
            "classification": entity.get("classification", ""),
            "lineage_upstream": entity.get("lineage", {}).get("upstream", []),
            "lineage_downstream": entity.get("lineage", {}).get("downstream", []),
            "security_notes": entity.get("security_notes", "")
        })

    return safe_entities


def get_audit_summary(
        user: dict,
        logs_dir: Path | str = "runtime/logs",
) -> list[dict]:
    """Return audit events safe for display in the UI.

    Admin sees all events. Non-admin sees only their own.

    Parameters
    ----------
    user
        Authenticated user record.
    logs_dir
        Directory for logs.

    Returns
    -------
    list[dict]
        Sanitized audit events.
    """
    return get_audit_summary_for_ui(user, logs_dir)
