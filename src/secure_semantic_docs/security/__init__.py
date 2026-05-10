"""Security package for secure-semantic-docs.

Public API re-exported from focused sub-modules:

- :mod:`.keyring_store` — key generation and OS-keyring loading
- :mod:`.secretbox_encryptor` — XSalsa20-Poly1305 encryption
- :mod:`.secretbox_decryptor` — XSalsa20-Poly1305 decryption
- :mod:`.chunk_field_encryptor` — chunk field encryption
- :mod:`.chunk_field_decryptor` — chunk field decryption
"""

from secure_semantic_docs.security.chunk_field_encryptor import encrypt_chunk_fields
from secure_semantic_docs.security.keyring_store import (
    generate_secret_key,
    resolve_key_material,
    resolve_secret_key
)

from secure_semantic_docs.security.secretbox_encryptor import (
    EMBEDDING_ENCRYPTION_ALGORITHM,
    secretbox_encrypt,
    secretbox_encrypt_str
)

__all__ = [
    "EMBEDDING_ENCRYPTION_ALGORITHM",
    "encrypt_chunk_fields",
    "generate_secret_key",
    "resolve_key_material",
    "resolve_secret_key",
    "secretbox_encrypt",
    "secretbox_encrypt_str"
]
