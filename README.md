![Python](https://img.shields.io/badge/python-3.14-blue)
![PySpark](https://img.shields.io/badge/pyspark-4.1.1-orange)
![PyNaCl](https://img.shields.io/badge/encryption-PyNaCl-purple)
![torch](https://img.shields.io/badge/torch-2.x-red)
![pytest](https://img.shields.io/badge/tested%20with-pytest-green)
![coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)
![version](https://img.shields.io/badge/version-0.5.0-informational)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

# Secure Semantic Docs

Secure Semantic Docs is a Python 3.14 and PySpark 4.1 secure document retrieval platform with a medallion lakehouse,
encrypted embeddings at rest, governed SQL views, and controlled semantic retrieval.

## Architecture summary

![Secure Semantic Docs Architecture](docs/assets/project_arch.png)

The platform enforces a single security rule throughout the stack:

**Filter first. Decrypt second. Search third. Audit always.**

Documents pass through Bronze → Silver → Gold parquet layers and are served via two governed paths:

- **Streamlit** — permission-first semantic retrieval with selective decryption.
- **Superset / Trino** — governed SQL exploration over `safe.*` views; no decryption.

See [docs/architecture.md](docs/architecture.md) for the full component diagram.

## Quick start

```bash
# Run the full enterprise stack
docker compose -f docker/docker-compose.yml up --build

# Ingest data (first time or refresh)
docker compose -f docker/docker-compose.yml --profile ingest up pipeline --build

# Start only the Streamlit UI
docker compose -f docker/docker-compose.yml --profile ui up --build

# Tear down
docker compose -f docker/docker-compose.yml down -v
```

## Access URLs

| Service   | URL                   |
|-----------|-----------------------|
| Streamlit | http://localhost:8501 |
| Superset  | http://localhost:8088 |
| Trino     | http://localhost:8080 |
| OPA       | http://localhost:8181 |

## Demo credentials

| Surface   | Username            | Password   | Notes     |
|-----------|---------------------|------------|-----------|
| Streamlit | `admin`             | `admin`    | Demo only |
| Streamlit | `business_analyst`  | `business` | Demo only |
| Streamlit | `security_engineer` | `security` | Demo only |
| Streamlit | `finance_manager`   | `finance`  | Demo only |
| Streamlit | `external_viewer`   | `external` | Demo only |
| Superset  | `admin`             | `admin`    | Demo only |

## Streamlit vs Superset

| UI        | Purpose                        | Allowed access                                    |
|-----------|--------------------------------|---------------------------------------------------|
| Streamlit | Semantic retrieval application | Permission-first search with selective decryption |
| Superset  | Governed SQL and dashboards    | `safe.*` views only, no decryption                |

See [docs/secure_ui.md](docs/secure_ui.md) for the UI security model.

## Security model summary

- Gold embeddings remain encrypted at rest with PyNaCl.
- `lakehouse.raw` is admin-only.
- Streamlit does not expose raw SQL.
- Superset does not expose raw schema or decryption paths.
- Audit logging remains part of the governed retrieval flow.

See [docs/security_boundaries.md](docs/security_boundaries.md) for the full security boundary model.

## Local pipeline demo

`src/secure_semantic_docs/demo.py` is a temporary local orchestrator that runs the full processing
pipeline — bronze → silver → gold ingestion, graph/facts build, Chroma sync, OpenMetadata export,
and quality checks — using only local Python and a local Spark session.

Its task-like functions are intentionally structured to map to individual Airflow tasks later.

```bash
python -m secure_semantic_docs.demo
```

Required steps (pipeline stops on failure):

- prepare runtime directories
- validate configuration
- validate input data
- bronze ingestion
- silver ingestion
- gold ingestion

Optional steps (logged and skipped on failure):

- graph/facts build
- Chroma index sync
- OpenMetadata export
- metadata quality checks

## Testing and coverage

Install development dependencies:

```bash
uv pip install -r requirements.txt -r requirements-dev.txt
# or
pip install -r requirements.txt -r requirements-dev.txt
```

Run the test suite:

```bash
pytest
```

Run tests with coverage (requires 100%):

```bash
pytest --cov=secure_semantic_docs --cov-report=term-missing
```

Run tests with an HTML coverage report:

```bash
pytest --cov=secure_semantic_docs --cov-report=term-missing --cov-report=html
```

The HTML report is generated at `htmlcov/index.html`.

## Project layout

```
src/secure_semantic_docs/   application and governance logic
config/                     contracts and service configuration (Trino, OPA, Streamlit)
data/                       input and demo documents
runtime/lakehouse/          Bronze, Silver, and Gold parquet outputs
runtime/logs/               audit and OpenMetadata-compatible exports
runtime/vector_store/       local Chroma persistence
docker/                     all Docker build files and Compose configuration
tests/                      unit and integration tests mirroring src/
```

## Documentation index

| Document                                                                   | Description                                             |
|----------------------------------------------------------------------------|---------------------------------------------------------|
| [Architecture](docs/architecture.md)                                       | Component diagram, medallion layers, end-to-end flow    |
| [Catalog and lineage](docs/catalog_and_lineage.md)                         | Bronze/Silver/Gold table registration and lineage edges |
| [Chroma index](docs/chroma_index.md)                                       | Vector store integration and embedding management       |
| [Contract-driven architecture](docs/contract_driven_architecture.md)       | Schema contracts and dataset contracts                  |
| [Future Airflow integration](docs/future_airflow_integration.md)           | Migrating demo.py task functions to an Airflow DAG      |
| [Future OpenMetadata integration](docs/future_openmetadata_integration.md) | Planned OpenMetadata server integration                 |
| [Future text model / RAG query](docs/future_text_model.md)                 | Planned LLM/RAG query flow with security requirements   |
| [Graph layer](docs/graph_layer.md)                                         | Fact extraction and graph-based retrieval               |
| [Permissions model](docs/permissions_model.md)                             | Role and clearance-based access control                 |
| [Secure UI](docs/secure_ui.md)                                             | Streamlit security model and retrieval flow             |
| [Security boundaries](docs/security_boundaries.md)                         | Layer-by-layer encryption and access boundaries         |
| [Trino, OPA, Superset](docs/trino_opa_superset.md)                         | Governed SQL stack configuration and integration        |

## Limitations

- Credentials and secrets in the Docker stack are demo-only.
- OPA policy is documented and containerised, but not yet wired into live Trino authorization calls.
- OpenMetadata is exported as JSON instead of running a full server by default.
- Superset exposes governed SQL metadata, not semantic retrieval results.
