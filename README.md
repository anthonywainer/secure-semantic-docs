![Python](https://img.shields.io/badge/python-3.14-blue)
![PySpark](https://img.shields.io/badge/pyspark-4.1.1-orange)
![pytest](https://img.shields.io/badge/tested%20with-pytest-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

# Secure Semantic Docs

A PySpark-based secure document ingestion and semantic search pipeline implementing a
medallion lakehouse architecture (bronze / silver / gold) with sensitivity detection,
permission metadata, and full provenance.

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

The pipeline is driven entirely by YAML. Loading order (each layer overrides the previous):

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
| `DOCSEC_ENV`          | Set to `prod` to activate the production config layer.                |

```bash
export DOCSEC_PROJECT_ROOT=$(pwd)
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

### Chunking configuration

Chunking parameters are set in `config.yml` and can be overridden locally:

```yaml
chunking:
  chunk_size: 400
  chunk_overlap: 80
  default_top_k: 5
  retrieval_candidate_multiplier: 4
```

---

## Running the pipelines

### Bronze ingestion

Reads raw document text and metadata, joins them, and writes a Parquet table.

```bash
export DOCSEC_PROJECT_ROOT=$(pwd)

uv run python -m secure_semantic_docs.bronze_ingestion
```

Steps:

1. Start a local Spark session
2. Load document metadata (JSON Lines)
3. Load raw document text files
4. Join documents with metadata
5. Write bronze Parquet to `$DOCSEC_PROJECT_ROOT/lakehouse/bronze_documents`

### Silver ingestion

Reads bronze documents, cleans text, chunks each document, runs synthetic
sensitivity detection on every chunk, and writes the silver Parquet table.

```bash
uv run python -m secure_semantic_docs.silver_ingestion
```

Steps:

1. Read bronze Parquet
2. Clean and chunk each document (word-boundary overlapping windows)
3. Enrich chunks with sensitivity score, detected types, encryption flags
4. Write silver Parquet to `$DOCSEC_PROJECT_ROOT/lakehouse/silver_chunks`

---

## Running the tests

```bash
uv run pytest tests/unit/ --cov=src --cov-report=term-missing
```

Run all tests including integration (requires a local Spark session, started automatically):

```bash
uv run pytest tests/ --cov=src --cov-report=term-missing
```

---

## Project structure

```
.
├── src/
│   └── secure_semantic_docs/
│       ├── core/               Settings, logging, Spark session factory,
│       │                       sensitivity detection, project metadata
│       ├── loader/             YAML config loader and builder
│       ├── models/             Frozen dataclasses: Config, SparkConfig,
│       │                       IcebergConfig, ChunkingConfig, readers, writers
│       ├── processing/         Text cleaning, word-boundary chunking
│       ├── storage/            DDL-based schema loader (bronze, silver)
│       ├── io/                 SparkReader / SparkWriter abstractions
│       ├── resources/          Bundled YAML configs, DDL files, synthetic data
│       ├── bronze_ingestion.py Bronze pipeline entry point
│       └── silver_ingestion.py Silver pipeline entry point
├── tests/
│   ├── unit/                   Fast, infrastructure-free unit tests
│   └── integration/            Tests requiring a live SparkSession
├── docker/                     Dockerfiles and docker-compose files
└── pyproject.toml
```

---

## Sensitivity detection

The silver pipeline tags every chunk with:

| Field                        | Type      | Description                                           |
|------------------------------|-----------|-------------------------------------------------------|
| `sensitivity_score`          | `float`   | 0.0 (public) to 1.0 (restricted + many PII patterns)  |
| `detected_sensitive_types`   | `list`    | e.g. `["email", "keyword:credential"]`                |
| `requires_encryption`        | `boolean` | `true` when score >= 0.5                              |
| `requires_restricted_access` | `boolean` | `true` when score >= 0.7                              |

Detection is a demo-level simulation using compiled regex patterns and a keyword
alternation regex. It is not a production PII engine.

---

## License

MIT. See [LICENSE](LICENSE) for details.

---

Secure Documents v0.2.0 -- [AnthonyWainer](mailto:awainerc@gmail.com)
