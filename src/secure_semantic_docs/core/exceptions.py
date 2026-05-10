class SecureSemanticDocsError(Exception):
    """Base exception for all project errors."""


class EmbeddingError(SecureSemanticDocsError):
    """Raised when embedding generation fails."""


class VectorStoreError(SecureSemanticDocsError):
    """Raised when a vector store operation fails."""


class EncryptionError(SecureSemanticDocsError):
    """Raised when encryption or decryption fails."""
