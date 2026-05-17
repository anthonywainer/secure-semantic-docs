"""Chroma vector candidate index client.

Chroma is a fast candidate index only — not the source of truth.
The encrypted lakehouse remains authoritative.

Safe metadata stored: chunk_id, document_id, classification,
allowed_roles, department, owner, version, sensitivity_level.

Never stored: chunk_text, raw_text, embedding_ciphertext,
embedding_nonce, key_id, or any secret keys.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from secure_semantic_docs.core.settings import BaseSettings

logger = logging.getLogger(BaseSettings.APP_NAME)

_COLLECTION_NAME = 'gold_embeddings_candidates'

_SAFE_METADATA_FIELDS: frozenset[str] = frozenset({
    'chunk_id',
    'document_id',
    'classification',
    'allowed_roles',
    'department',
    'owner',
    'version',
    'sensitivity_level'
})

_FORBIDDEN_PAYLOAD_FIELDS: frozenset[str] = frozenset({
    'chunk_text',
    'raw_text',
    'embedding_ciphertext',
    'embedding_nonce',
    'key_id',
    'secret',
    'password'
})


@dataclass
class ChromaConfig:
    """Configuration for the Chroma vector index client.

    Attributes
    ----------
    host
        Chroma server hostname. Defaults to CHROMA_HOST env var or 'localhost'.
    port
        Chroma server port. Defaults to CHROMA_PORT env var or 8000.
    collection_name
        Name of the Chroma collection. Defaults to the canonical collection name.
    persist_path
        Local path for Chroma persistence (used in embedded mode only).
    """

    host: str = field(default_factory=lambda: os.environ.get('CHROMA_HOST', 'localhost'))
    port: int = field(default_factory=lambda: int(os.environ.get('CHROMA_PORT', '8000')))
    collection_name: str = _COLLECTION_NAME
    persist_path: Path | None = None


def connect_chroma(config: ChromaConfig | None = None) -> Any:
    """Connect to the Chroma HTTP server and return a collection handle.

    Parameters
    ----------
    config
        Chroma configuration. Defaults to ChromaConfig() which reads env vars.

    Returns
    -------
    Any
        The Chroma collection for gold embedding candidates.

    Raises
    ------
    ImportError
        When chromadb is not installed.
    RuntimeError
        When the Chroma server is unreachable.
    """
    try:
        import chromadb  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            'chromadb is required for vector index integration. '
            'Install with: pip install chromadb'
        ) from exc

    if config is None:
        config = ChromaConfig()

    try:
        client = chromadb.HttpClient(host=config.host, port=config.port)
        collection = client.get_or_create_collection(
            name=config.collection_name,
            metadata={'hnsw:space': 'cosine'}
        )
    except Exception as exc:
        raise RuntimeError(
            f'Could not connect to Chroma at {config.host}:{config.port}: {exc}'
        ) from exc

    logger.info(
        'Connected to Chroma at %s:%s collection=%s',
        config.host,
        config.port,
        config.collection_name
    )
    return collection


def build_safe_metadata(record: dict[str, Any]) -> dict[str, Any]:
    """Extract safe metadata fields from a gold record for Chroma storage.

    Only whitelisted safe fields are included. Forbidden fields are explicitly
    excluded regardless of input.

    Parameters
    ----------
    record
        A gold embedding record (may contain sensitive fields).

    Returns
    -------
    dict[str, Any]
        Safe metadata dict suitable for Chroma document metadata.
    """
    metadata: dict[str, Any] = {}

    for field_name in _SAFE_METADATA_FIELDS:
        if field_name in _FORBIDDEN_PAYLOAD_FIELDS:
            continue

        value = record.get(field_name)
        if value is None or isinstance(value, bytes | bytearray):
            continue

        if isinstance(value, list):
            metadata[field_name] = ','.join(str(item) for item in value)
            continue

        metadata[field_name] = value

    for forbidden_name in _FORBIDDEN_PAYLOAD_FIELDS:
        metadata.pop(forbidden_name, None)

    return metadata


def upsert_candidates(
        collection: Any,
        records: list[dict[str, Any]],
        embeddings: list[list[float]]
) -> int:
    """Upsert gold embedding candidates into Chroma.

    Parameters
    ----------
    collection
        Chroma collection handle from :func:`connect_chroma`.
    records
        Gold embedding records. Safe metadata is extracted from each.
    embeddings
        Decoded float embedding vectors corresponding to each record.
        Must have the same length as records.

    Returns
    -------
    int
        Number of records upserted.
    """
    if len(records) != len(embeddings):
        raise ValueError(
            f'records ({len(records)}) and embeddings ({len(embeddings)}) length mismatch'
        )

    ids: list[str] = []
    metadatas: list[dict[str, Any]] = []
    vectors: list[list[float]] = []

    for record, embedding in zip(records, embeddings, strict=False):
        chunk_id = record.get('chunk_id') or record.get('embedding_id', '')
        if not chunk_id:
            logger.warning(
                'Skipping record without chunk_id: %s',
                record.get('embedding_id')
            )
            continue
        ids.append(str(chunk_id))
        metadatas.append(build_safe_metadata(record))
        vectors.append(embedding)

    if not ids:
        logger.warning('No valid records to upsert into Chroma')
        return 0

    collection.upsert(ids=ids, embeddings=vectors, metadatas=metadatas)
    logger.info('Upserted %d candidates into Chroma collection', len(ids))
    return len(ids)


def query_candidates(
        collection: Any,
        query_embedding: list[float],
        top_k: int = 20,
        where: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Query Chroma for nearest-neighbor candidate chunk IDs.

    Parameters
    ----------
    collection
        Chroma collection handle from :func:`connect_chroma`.
    query_embedding
        Query vector as a list of floats.
    top_k
        Maximum number of candidates to return (pre-permission filter).
    where
        Optional Chroma metadata filter expression.

    Returns
    -------
    list[dict[str, Any]]
        Candidate records with chunk_id, document_id, classification,
        distance, and safe metadata fields.
    """
    query_kwargs: dict[str, Any] = {
        'query_embeddings': [query_embedding],
        'n_results': top_k,
        'include': ['metadatas', 'distances']
    }
    if where:
        query_kwargs['where'] = where

    results = collection.query(**query_kwargs)

    candidates: list[dict[str, Any]] = []
    ids = results.get('ids', [[]])[0]
    metadatas = results.get('metadatas', [[]])[0]
    distances = results.get('distances', [[]])[0]

    for chunk_id, metadata, distance in zip(ids, metadatas, distances, strict=False):
        candidate = dict(metadata or {})
        candidate['chunk_id'] = chunk_id
        candidate['_chroma_distance'] = float(distance)
        candidates.append(candidate)

    return candidates
