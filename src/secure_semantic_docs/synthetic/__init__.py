"""Data generation package for secure-semantic-docs.

Sub-modules
-----------
generator  -- synthetic enterprise document and user generation
"""

from secure_semantic_docs.synthetic.generator import (
    generate_documents,
    generate_users,
    save_dataset
)

__all__ = ["generate_documents", "generate_users", "save_dataset"]
