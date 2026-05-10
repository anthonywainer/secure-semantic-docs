"""Partition-level embedding encoding and encryption helpers."""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping
from typing import Any, cast

from pyspark.sql import Row

from secure_semantic_docs.core.exceptions import EmbeddingError
from secure_semantic_docs.embeddings.model_loader import load_cached_model
from secure_semantic_docs.embeddings.typing import (
    EmbeddingMatrix,
    EmbeddingModel,
    EmbeddingRow
)
from secure_semantic_docs.embeddings.worker_env import (
    configure_worker_environment,
    worker_safe_device
)
from secure_semantic_docs.processing.chunk_texts import chunk_texts
from secure_semantic_docs.security.secretbox_encryptor import EMBEDDING_ENCRYPTION_ALGORITHM


def encode_and_encrypt_partition(
        rows: Iterator[Row],
        model_name: str,
        device: str,
        batch_size: int,
        normalize: bool,
        created_at: str,
        encryption_key: bytes,
        key_id: str,
        embedding_dim: int,
        embedding_dtype: str,
        raw_docs_dir: str
) -> Iterator[EmbeddingRow]:
    """Embed all chunks in one Spark partition and encrypt each vector.

    Called inside each executor process. All parameters are plain Python
    scalars or ``bytes`` so the closure is safely picklable across the driver /
    executor boundary. ``configure_worker_environment`` is called first to set
    the necessary env vars before any ``sentence_transformers`` import.

    The full partition is materialised into a list so all chunk texts can be
    encoded in a single batched ``sentence_transformer.encode`` call; partition
    memory is bounded by Spark's configured memory per executor.

    After encoding, each float32 vector is serialised to raw bytes via
    :func:`~secure_semantic_docs.embeddings.serializer.ndarray_to_bytes` (a
    direct ``astype(float32).tobytes()`` on the numpy row, no list round-trip)
    and then encrypted with
    :func:`~secure_semantic_docs.security.secretbox_encryptor.secretbox_encrypt`.
    Plaintext vectors are discarded immediately after encryption — they are
    never yielded or persisted.

    Parameters
    ----------
    rows:
        Partition iterator provided by ``mapPartitions``.
    model_name:
        HuggingFace model identifier.
    device:
        Concrete device string (``"cpu"``, ``"cuda"``, ``"mps"``).
    batch_size:
        Texts per forward pass.
    normalize:
        Whether to L2-normalise output vectors.
    created_at:
        ISO-8601 timestamp string to stamp on every output row.
    encryption_key:
        32-byte secret key. Passed as a raw ``bytes`` scalar so pickling
        works across the Spark driver / executor boundary.
    key_id:
        Stable identifier for *encryption_key*. Safe to log and store.
    embedding_dim:
        Expected vector dimensionality. Stored with each row to allow
        correct deserialisation during search.
    embedding_dtype:
        Numpy dtype string (e.g. ``"float32"``). Stored alongside
        ``embedding_dim`` for round-trip fidelity.
    raw_docs_dir:
        Directory containing the raw source documents used to reconstruct
        chunk text from ``chunk_span``.
    """
    configure_worker_environment()
    loaded_model: object = load_cached_model(model_name, worker_safe_device(device))
    sentence_transformer = cast(
        EmbeddingModel,
        loaded_model
    )

    chunk_rows = [chunk_row.asDict() for chunk_row in rows]
    if not chunk_rows:
        return

    texts = chunk_texts(chunk_rows, raw_docs_dir)
    embedding_matrix = _encode_texts(
        sentence_transformer,
        texts,
        model_name,
        normalize,
        batch_size
    )

    for chunk_fields, row_vector in zip(chunk_rows, embedding_matrix, strict=True):
        yield _embedding_row(
            chunk_fields,
            row_vector,
            encryption_key,
            embedding_dim,
            embedding_dtype,
            model_name,
            key_id,
            created_at
        )


def _encode_texts(
        sentence_transformer: EmbeddingModel,
        texts: list[str],
        model_name: str,
        normalize: bool,
        batch_size: int
) -> EmbeddingMatrix:
    try:
        return sentence_transformer.encode(
            texts,
            normalize_embeddings=normalize,
            show_progress_bar=False,
            batch_size=batch_size
        )
    except Exception as exc:
        raise EmbeddingError(
            f'Batch encode failed -- model={model_name} '
            f'partition_size={len(texts)}: {exc}'
        ) from exc


def _embedding_row(
        chunk_fields: Mapping[str, Any],
        row_vector,
        encryption_key: bytes,
        embedding_dim: int,
        embedding_dtype: str,
        model_name: str,
        key_id: str,
        created_at: str
) -> EmbeddingRow:
    from secure_semantic_docs.embeddings.serializer import ndarray_to_bytes  # noqa: PLC0415
    from secure_semantic_docs.security.secretbox_encryptor import secretbox_encrypt  # noqa: PLC0415

    raw_bytes = ndarray_to_bytes(row_vector)
    ciphertext, nonce = secretbox_encrypt(raw_bytes, encryption_key)

    return (
        str(uuid.uuid4()),
        str(chunk_fields['chunk_id']),
        str(chunk_fields['document_id']),
        ciphertext,
        nonce,
        EMBEDDING_ENCRYPTION_ALGORITHM,
        embedding_dim,
        embedding_dtype,
        model_name,
        key_id,
        _optional_str(chunk_fields.get('classification')),
        _optional_list(chunk_fields.get('allowed_roles')),
        _optional_str(chunk_fields.get('owner')),
        _optional_str(chunk_fields.get('department')),
        _optional_str(chunk_fields.get('source_path')),
        _optional_str(chunk_fields.get('version')),
        _optional_str(chunk_fields.get('document_hash')),
        created_at
    )


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_list(value: object) -> list | None:
    return value if isinstance(value, list) else None
