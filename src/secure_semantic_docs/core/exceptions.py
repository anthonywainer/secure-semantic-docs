class SecureSemanticDocsError(Exception):
    """Base exception for all project errors."""


class EmbeddingError(SecureSemanticDocsError):
    """Raised when embedding generation fails."""
