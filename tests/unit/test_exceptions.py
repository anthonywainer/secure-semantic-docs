"""Tests for the custom exception hierarchy."""

import pytest

from secure_semantic_docs.exceptions import (
    ConfigurationError,
    EmbeddingError,
    EncryptionError,
    IngestionError,
    PermissionDeniedError,
    SecureSemanticDocsError,
    VectorStoreError,
)


class TestExceptionHierarchy:
    def test_base_is_exception(self):
        assert issubclass(SecureSemanticDocsError, Exception)

    def test_configuration_error_is_base(self):
        assert issubclass(ConfigurationError, SecureSemanticDocsError)

    def test_encryption_error_is_base(self):
        assert issubclass(EncryptionError, SecureSemanticDocsError)

    def test_permission_denied_error_is_base(self):
        assert issubclass(PermissionDeniedError, SecureSemanticDocsError)

    def test_embedding_error_is_base(self):
        assert issubclass(EmbeddingError, SecureSemanticDocsError)

    def test_vector_store_error_is_base(self):
        assert issubclass(VectorStoreError, SecureSemanticDocsError)

    def test_ingestion_error_is_base(self):
        assert issubclass(IngestionError, SecureSemanticDocsError)


class TestExceptionRaisable:
    @pytest.mark.parametrize(
        "exc_class",
        [
            SecureSemanticDocsError,
            ConfigurationError,
            EncryptionError,
            PermissionDeniedError,
            EmbeddingError,
            VectorStoreError,
            IngestionError,
        ],
    )
    def test_can_raise_and_catch(self, exc_class):
        with pytest.raises(exc_class, match="test message"):
            raise exc_class("test message")

    def test_base_catches_subclass(self):
        with pytest.raises(SecureSemanticDocsError):
            raise IngestionError("caught by base")
