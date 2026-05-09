![Python](https://img.shields.io/badge/python-3.14-blue)
![PySpark](https://img.shields.io/badge/pyspark-4.1.1-orange)
![pytest](https://img.shields.io/badge/tested%20with-pytest-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

# Secure Semantic Docs

A PySpark-based secure document ingestion and semantic search pipeline implementing a
medallion lakehouse architecture (bronze / silver / gold) with sensitivity detection,
permission metadata, vector embeddings, and full provenance.

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

```yaml
chunking:
  chunk_size: 400
  chunk_overlap: 80
  default_top_k: 5
  retrieval_candidate_multiplier: 4
```

### Embedding configuration

```yaml
embedding:
  model: all-MiniLM-L6-v2   # HuggingFace model identifier
  device: auto               # auto | cpu | cuda | cuda:0 | mps
  batch_size: 64             # chunks per encode() call
  normalize: true            # cosine-similarity-ready unit vectors
  num_partitions: 0          # 0 = 1 partition per executor core (recommended)
```

`device: auto` probes CUDA → MPS → CPU in that order. On Apple Silicon, MPS is used
on the driver for logging purposes; Spark workers always run on CPU because Metal
cannot be accessed from forked subprocesses.

`num_partitions: 0` applies the Spark best practice for CPU-bound workloads: one
partition per executor core. In local mode the count is always capped at 1 to prevent
every worker process from loading the model simultaneously.

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

### Gold ingestion

Reads silver chunks, generates dense vector embeddings using SentenceTransformers,
and writes the gold Parquet table ready for semantic search.

```bash
uv run python -m secure_semantic_docs.gold_ingestion
```

Steps:

1. Read silver Parquet
2. Drop null or empty `chunk_text` rows
3. Repartition to one partition per executor core (capped at 1 in local mode)
4. Generate embeddings partition-by-partition using `mapPartitions` — the model
   loads once per worker process and is cached for the process lifetime
5. Write gold Parquet to `$DOCSEC_PROJECT_ROOT/lakehouse/gold_embeddings`

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
│       ├── embeddings/         SentenceTransformer model loading, worker
│       │                       environment setup, partition-level encoding
│       ├── loader/             YAML config loader and builder
│       ├── models/             Frozen dataclasses: Config, SparkConfig,
│       │                       IcebergConfig, ChunkingConfig, EmbeddingConfig,
│       │                       readers, writers
│       ├── processing/         Text cleaning, word-boundary chunking
│       ├── storage/            DDL-based schema loader (bronze, silver, gold)
│       ├── io/                 SparkReader / SparkWriter abstractions
│       ├── resources/          Bundled YAML configs, DDL files, synthetic data
│       ├── bronze_ingestion.py Bronze pipeline entry point
│       ├── silver_ingestion.py Silver pipeline entry point
│       └── gold_ingestion.py   Gold pipeline entry point (embeddings)
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

## Embedding design notes

- **Model caching** — `_MODEL_CACHE` in `model_loader.py` stores one model instance
  per `(model_name, device)` key per worker process. Combined with
  `spark.python.worker.reuse=true`, each worker loads the model exactly once
  regardless of how many partitions it processes.

- **MPS / Apple Silicon** — MPS is subprocess-unsafe (Metal holds OS-level resources
  tied to the parent process). `worker_safe_device()` silently remaps `"mps"` →
  `"cpu"` inside every Spark worker, while the driver logs the resolved device
  correctly for observability.

- **Partition count** — For CPU-intensive workloads, the Spark best practice is 1
  partition per core, not 2–4× (which is for IO/shuffle jobs). In local mode the
  count is always 1: multiple workers would each load the full model, causing OOM.

- **Null filtering** — Null and empty `chunk_text` rows are dropped before
  repartitioning so no executor wastes time on encode calls that produce nothing.

---

## License

MIT. See [LICENSE](LICENSE) for details.

---

Secure Documents v0.3.0 -- [AnthonyWainer](mailto:awainerc@gmail.com)
