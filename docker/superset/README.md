# Superset SQL UI Build

The Superset Docker build file lives at `docker/superset/`.
Runtime Superset configuration lives at `config/superset/`.

## Files

```text
docker/superset/
└── Dockerfile          # Extends apache/superset with Trino connector

config/superset/
├── superset_config.py  # PostgreSQL backend, CSRF config
└── init_superset.sh    # Creates demo users and registers Trino DB
```

## Port

Superset runs on port `8088`.

## Demo credentials

| User              | Password |
|-------------------|----------|
| admin             | admin    |
| business_analyst  | business |
| security_engineer | security |
| finance_manager   | finance  |
| external_viewer   | external |

## Role

Superset is a **governed SQL UI** connected to Trino.
It exposes only `lakehouse.safe.*` views.
It does NOT perform semantic retrieval — that is Streamlit's role.

## Governed datasets

- `safe.v_bronze_documents_catalog`
- `safe.v_silver_chunks_catalog`
- `safe.v_gold_embedding_catalog`
- `safe.v_public_chunks`
- `safe.v_internal_chunks`
- `safe.v_audit_events` (admin only)
