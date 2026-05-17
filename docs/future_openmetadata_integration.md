# Future OpenMetadata integration

## Current state

This demo does not require a full OpenMetadata deployment.
Instead, the governance layer exports an OpenMetadata-compatible JSON document at
`runtime/logs/openmetadata_assets.json`.
That export is enough to document the platform graph, lineage, and governed assets for local demos.

## What the export includes

The current export includes:

- landing, bronze, silver, and gold lakehouse assets
- Trino governed SQL views
- Superset SQL UI
- Streamlit governed retrieval UI
- audit lineage

## Running full OpenMetadata later

A future full deployment can run beside this repository with Docker Compose.
A minimal sketch looks like this:

```yaml
services:
  openmetadata-server:
    image: openmetadata/server:1.5.7
    ports:
      - "8585:8585"
  openmetadata-ingestion:
    image: openmetadata/ingestion:1.5.7
    depends_on:
      - openmetadata-server
```

After the service is up, the exported JSON can be imported through ingestion workflows or the metadata APIs.

## Lineage in the UI

The expected lineage would show:

- Landing → Bronze → Silver → Gold Encrypted Embeddings
- Gold Encrypted Embeddings → Trino Governed Views → Superset SQL UI
- Gold Encrypted Embeddings → Secure Retrieval Service → Streamlit Governed UI
- Secure Retrieval Service → Audit Events

## Why full deployment is optional

Full OpenMetadata is useful for enterprise rollout, but it is heavy for a local demo. The JSON export gives the project
a lightweight governance artifact without adding another always-on platform dependency.
