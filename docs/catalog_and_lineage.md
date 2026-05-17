# Catalog and Lineage

## Overview

The platform generates an OpenMetadata-compatible JSON catalog documenting all
data assets, their classifications, ownership, and lineage.

## Asset Lineage

```
landing_documents
    → bronze_documents      (ingestion)
    → silver_chunks         (transformation: chunking + sensitivity)
    → gold_embeddings       (transformation: encrypted embeddings)
    → secure_retrieval      (service: permission-aware search)
    → streamlit_governed_ui (presentation: controlled UI)
    → audit_events          (logging: immutable audit trail)
```

## Generating the Catalog

```python
from secure_semantic_docs.governance import export_openmetadata_catalog

export_openmetadata_catalog(
    output_path="runtime/logs/openmetadata_assets.json",
    project_root="."
)
```

Or via the demo:

```bash
python -m secure_semantic_docs.demo
```

Output: `runtime/logs/openmetadata_assets.json`

## Asset Descriptions

| Asset                   | Type        | Layer  | Classification |
|-------------------------|-------------|--------|----------------|
| `landing_documents`     | Table       | —      | public         |
| `bronze_documents`      | Table       | bronze | mixed          |
| `silver_chunks`         | Table       | silver | mixed          |
| `gold_embeddings`       | Table       | gold   | confidential   |
| `secure_retrieval`      | API         | —      | —              |
| `streamlit_governed_ui` | Application | —      | —              |
| `audit_events`          | Log         | —      | —              |

## Security Notes

- Gold embeddings contain only encrypted ciphertexts. Plaintext vectors are never stored.
- The Streamlit UI does not expose raw table data or direct SQL access.
- Direct SQL engines (Trino, Superset) are intentionally excluded from the lineage.
