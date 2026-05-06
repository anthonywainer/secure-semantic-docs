![Python](https://img.shields.io/badge/python-3.14-blue)
![PySpark](https://img.shields.io/badge/pyspark-4.1.1-orange)
![pytest](https://img.shields.io/badge/tested%20with-pytest-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

# Secure Semantic Docs
Secure semantic document search pipeline built on PySpark

---

## Requirements

- Python 3.14+
- Java 11+ (required by PySpark)
- `uv` (recommended) or `pip`

---

## Installation

```bash
git clone https://github.com/anthonywainer/secure-semantic-docs.git
cd secure-semantic-docs

uv sync --group dev
```

Or with plain pip:

```bash
pip install -e ".[dev]"
```

---

## Configuration

The pipeline is driven entirely by YAML files. Loading order (each layer overrides the previous):

| File                                                 | Description                             |
|------------------------------------------------------|-----------------------------------------|
| `src/secure_semantic_docs/resources/config.yml`      | Bundled base defaults                   |
| `src/secure_semantic_docs/resources/config.dev.yml`  | Dev overrides (always applied)          |
| `src/secure_semantic_docs/resources/config.prod.yml` | Prod overrides (`DOCSEC_ENV=prod` only) |
| `config.local.yml`                                   | Machine-local overrides, git-ignored    |

### Environment variables

| Variable              | Description                                                           |
|-----------------------|-----------------------------------------------------------------------|
| `DOCSEC_PROJECT_ROOT` | Project root directory. Defaults to the repository root when not set. |
| `DOCSEC_ENV`          | Set to `prod` to activate production config.                          |

Export before running:

```bash
export DOCSEC_PROJECT_ROOT=/path/to/secure-semantic-docs
```

### Local overrides

Create `config.local.yml` at the project root to override any value locally:

```yaml
spark_confs:
  spark.driver.memory: 4g

writers:
  bronze_documents:
    options:
      path: "/data/lake/bronze_documents"
```

---

## Running the bronze ingestion pipeline

```bash
export DOCSEC_PROJECT_ROOT=$(pwd)

uv run python -m secure_semantic_docs.bronze_ingestion
```

The pipeline steps are:

1. Start a Spark session
2. Load document metadata (JSON)
3. Load raw document text files
4. Join documents with metadata
5. Write the bronze Parquet table to `$DOCSEC_PROJECT_ROOT/lakehouse/bronze_documents`

---

## Running the tests

```bash
uv run pytest tests/unit/ --cov=src --cov-report=term-missing
```

---

## Project structure

```
.
├── src/
│   └── secure_semantic_docs/
│       ├── core/                  Logging, settings, exceptions, Spark session factory
│       ├── loader/                YAML config loader and builder
│       ├── models/                Dataclasses for config, readers, writers, Spark/Iceberg
│       ├── storage/               DDL-based schema loader
│       ├── resources/             Bundled YAML configs and DDL schema files
│       ├── ingestion/             PySpark readers and parsers (bronze layer)
│       ├── processing/            Text cleaning, chunking, metadata enrichment, PII detection
│       ├── embeddings/            SentenceTransformers model loading and embedding generation
│       ├── vector_store/          Chroma client wrapper
│       ├── lakehouse/             Iceberg read/write helpers (bronze / silver / gold)
│       ├── governance/            OpenMetadata API client and lineage registration
│       ├── security/              PyNaCl encryption/decryption utilities, permission enforcement
│       ├── api/                   Serving layer (semantic search, role-based query endpoints)
│       └── bronze_ingestion.py    Bronze pipeline entry point
├── tests/
│   └── unit/                      Fast, infrastructure-free unit tests
├── docker/                        Dockerfiles and docker-compose files
└── pyproject.toml
```

---

## License

MIT. See [LICENSE](LICENSE) for details.

---

Secure Documents v0.1.0 — @author anthony_wainer