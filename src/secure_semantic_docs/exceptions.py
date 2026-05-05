"""Custom exception types for secure-semantic-docs."""


class SecureSemanticDocsError(Exception):
    """Base exception for all project errors."""


class ConfigurationError(SecureSemanticDocsError):
    """Raised when configuration is invalid or missing."""


class EncryptionError(SecureSemanticDocsError):
    """Raised when encryption or decryption fails."""


class PermissionDeniedError(SecureSemanticDocsError):
    """Raised when a user attempts to access unauthorized content."""


class EmbeddingError(SecureSemanticDocsError):
    """Raised when embedding generation fails."""


class VectorStoreError(SecureSemanticDocsError):
    """Raised when a vector store operation fails."""


class IngestionError(SecureSemanticDocsError):
    """Raised when document ingestion fails."""
