"""secure-semantic-docs: secure semantic document search with PySpark.

Package layout
--------------
config      -- YAML-driven configuration (Config, load_config)
pipeline    -- bronze / silver / gold PySpark pipeline
storage     -- Parquet lakehouse and Chroma vector-store wrappers
security    -- PyNaCl encryption and RBAC permissions
search      -- insecure_search, secure_search, and audit logging
data        -- synthetic dataset generation
exceptions  -- custom exception hierarchy
"""

__version__ = "0.1.0"
