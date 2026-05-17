"""Access context dataclass for retrieval requests."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class AccessContext:
    """Encapsulates all context needed for a retrieval request.

    Attributes
    ----------
    user
        Authenticated user record. None if unauthenticated.
    user_id
        User identifier string.
    query
        Search query text.
    top_k
        Maximum number of results to return.
    logs_dir
        Directory for writing audit logs.
    encryption_key
        Optional symmetric key for decrypting embeddings.
    retrieval_strategy
        One of: 'vector_first', 'graph_first', 'hybrid'. Default: 'hybrid'.
    """

    user: dict | None
    user_id: str
    query: str
    top_k: int
    logs_dir: Path
    encryption_key: bytes | None = None
    retrieval_strategy: str = 'hybrid'

    @property
    def role(self) -> str:
        """Return the role string for the user, or 'unknown' if unauthenticated."""
        if self.user is None:
            return 'unknown'
        return self.user.get('role', 'unknown')
