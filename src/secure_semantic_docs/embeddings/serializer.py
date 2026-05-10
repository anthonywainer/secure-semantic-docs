"""Embedding vector serialization for encrypted storage.

Converts float32 embedding vectors to raw bytes for encryption and back
to numpy arrays after decryption.  Storing raw ``float32`` bytes is the
most compact and reversible representation: an N-dimensional vector
occupies exactly ``N × 4`` bytes with no header overhead.

The embedding dimension (``embedding_dim``) and dtype (``embedding_dtype``)
are stored as separate columns rather than being embedded in the byte payload.
This keeps the serialization format trivial and avoids any home-grown framing
protocol.

Usage inside a Spark worker
---------------------------
Serialization runs inside ``embed_partition`` (the ``mapPartitions`` closure)
so it must import only standard-library and numpy — never PySpark classes.
``numpy`` is always available because ``sentence-transformers`` depends on it.
"""

from __future__ import annotations

import numpy as np

EMBEDDING_DTYPE: str = "float32"
"""Canonical dtype for stored embedding vectors.

All vectors are cast to ``float32`` before serialization.  Downstream
consumers must pass this string to :func:`bytes_to_embedding` to recover
the original precision.
"""


def embedding_to_bytes(vector: list[float]) -> bytes:
    """Serialize a float32 embedding vector to raw bytes.

    Parameters
    ----------
    vector:
        Embedding output from ``SentenceTransformer.encode(...).tolist()``.
        Values are cast to ``float32`` regardless of their original precision.

    Returns
    -------
    bytes
        Raw little-endian IEEE 754 float32 representation — ``len(vector) × 4``
        bytes.  Pass to :func:`bytes_to_embedding` with the original dimension
        to reconstruct the array.
    """
    return np.array(vector, dtype=np.float32).tobytes()


def ndarray_to_bytes(array: np.ndarray) -> bytes:
    """Serialize a numpy embedding array to raw bytes without a list round-trip.

    Prefer this over :func:`embedding_to_bytes` when you already hold a numpy
    array (e.g. a row slice from the batched ``SentenceTransformer.encode``
    result).  When the array is already ``float32`` the cast is a no-op and
    no extra copy is made.

    Parameters
    ----------
    array:
        1-D numpy array of any floating-point dtype.

    Returns
    -------
    bytes
        Raw little-endian IEEE 754 float32 bytes — ``len(array) × 4`` bytes.
    """
    return array.astype(np.float32, copy=False).tobytes()


def bytes_to_embedding(data: bytes, dim: int, dtype: str = EMBEDDING_DTYPE) -> np.ndarray:
    """Deserialize raw bytes back to a numpy embedding array.

    Parameters
    ----------
    data:
        Bytes produced by :func:`embedding_to_bytes` (or equivalently by
        ``np.array(vector, dtype=np.float32).tobytes()``).
    dim:
        Expected number of dimensions.  Used to validate that the byte
        length is consistent with the declared dtype.
    dtype:
        Numpy dtype string.  Must match the dtype used at serialization time.
        Defaults to :data:`EMBEDDING_DTYPE` (``"float32"``).

    Returns
    -------
    numpy.ndarray
        1-D array of shape ``(dim),`` with the given dtype.

    Raises
    ------
    ValueError
        When the byte length is inconsistent with ``dim × itemsize``.
    """
    arr = np.frombuffer(data, dtype=np.dtype(dtype))
    expected_len = dim
    if len(arr) != expected_len:
        raise ValueError(
            f"Byte payload has {len(arr)} elements but expected {expected_len} "
            f"for dim={dim} dtype={dtype}"
        )
    return arr
