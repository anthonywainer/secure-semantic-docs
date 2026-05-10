"""Unit tests for embedding serialization."""

import numpy as np
import pytest

from secure_semantic_docs.embeddings.serializer import (
    EMBEDDING_DTYPE,
    bytes_to_embedding,
    embedding_to_bytes
)


class TestEmbeddingToBytes:
    def test_round_trip_float_list(self):
        vector = [0.1, 0.2, 0.3, 0.4]
        result = bytes_to_embedding(embedding_to_bytes(vector), dim=4)
        np.testing.assert_allclose(result, np.array(vector, dtype=np.float32), rtol=1e-6)

    def test_output_is_bytes(self):
        assert isinstance(embedding_to_bytes([1.0, 2.0]), bytes)

    def test_byte_length_is_four_times_dim(self):
        dim = 8
        assert len(embedding_to_bytes([0.0] * dim)) == dim * 4

    def test_casts_float64_to_float32(self):
        vector = [float(1) / 3] * 4
        raw = embedding_to_bytes(vector)
        recovered = bytes_to_embedding(raw, dim=4)
        assert recovered.dtype == np.float32

    def test_zero_vector(self):
        raw = embedding_to_bytes([0.0, 0.0])
        result = bytes_to_embedding(raw, dim=2)
        np.testing.assert_array_equal(result, np.zeros(2, dtype=np.float32))


class TestBytesToEmbedding:
    def test_returns_numpy_array(self):
        raw = embedding_to_bytes([1.0, 2.0, 3.0])
        result = bytes_to_embedding(raw, dim=3)
        assert isinstance(result, np.ndarray)

    def test_default_dtype_is_float32(self):
        raw = embedding_to_bytes([1.0, 2.0])
        result = bytes_to_embedding(raw, dim=2)
        assert result.dtype == np.dtype(EMBEDDING_DTYPE)

    def test_custom_dtype_applied(self):
        arr = np.array([1.0, 2.0], dtype=np.float64)
        raw = arr.tobytes()
        result = bytes_to_embedding(raw, dim=2, dtype="float64")
        assert result.dtype == np.float64

    def test_wrong_dim_raises_value_error(self):
        raw = embedding_to_bytes([1.0, 2.0, 3.0])
        with pytest.raises(ValueError, match="3 elements but expected 5"):
            bytes_to_embedding(raw, dim=5)

    def test_single_element(self):
        raw = embedding_to_bytes([0.5])
        result = bytes_to_embedding(raw, dim=1)
        np.testing.assert_allclose(result[0], 0.5, rtol=1e-6)
