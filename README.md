![Python](https://img.shields.io/badge/python-3.14-blue)
![PySpark](https://img.shields.io/badge/pyspark-4.1.1-orange)
![PyNaCl](https://img.shields.io/badge/encryption-PyNaCl-purple)
![torch](https://img.shields.io/badge/torch-2.x-red)
![pytest](https://img.shields.io/badge/tested%20with-pytest-green)
![coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)
![version](https://img.shields.io/badge/version-0.4.0-informational)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

# Secure Semantic Docs

A PySpark-based secure document ingestion pipeline for a document lakehouse. It
keeps raw document text out of downstream tables, stores chunk metadata separately
from encrypted embedding vectors, and carries sensitivity, permission, and
provenance fields through the pipeline.

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

readers:
  raw_documents:
    options:
      path: "/data/raw_documents"

  embed_cache:
    options:
      path: "/data/lake/embed_cache"

writers:
  bronze_documents:
    options:
      path: "/data/lake/bronze_documents"

  embed_cache:
    options:
      path: "/data/lake/embed_cache"
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

Reads bronze document metadata, builds a transient chunk workset, writes persisted
chunk metadata, generates encrypted embeddings, and writes the embedding table.
The transient workset includes plaintext `chunk_text` only in Spark execution
memory so embedding inference can run without storing raw chunk text in the
lakehouse.

```bash
uv run python -m secure_semantic_docs.gold_ingestion
```

Steps:

1. Read bronze Parquet metadata
2. Re-read source document text from the configured `raw_documents` reader
3. Build a transient chunk workset with sensitivity fields and `chunk_text`
4. Write persisted chunk metadata to `$DOCSEC_PROJECT_ROOT/lakehouse/silver_chunks`
5. Reuse compatible encrypted embeddings from `$DOCSEC_PROJECT_ROOT/lakehouse/embed_cache`
6. Generate missing embeddings partition-by-partition using `mapPartitions`; the model
   loads once per worker process and is cached for the process lifetime
7. Encrypt every fresh embedding vector with PyNaCl `SecretBox`
8. Append fresh encrypted embeddings to the internal cache
9. Write encrypted embeddings to `$DOCSEC_PROJECT_ROOT/lakehouse/gold_embeddings`

The cache is keyed by `(chunk_id, document_hash)` and is reused only when the
model name, embedding dimension, and encryption `key_id` match the current run.
Cache hits skip `model.encode()` and are mapped directly into the embedding
schema. Cache misses are encoded, encrypted, written to the cache, and included
in the final output.

---

## Running the tests

Run the fast unit suite:

```bash
uv run pytest tests/unit/ -q
```

Run the full suite with coverage:

```bash
uv run pytest tests/ --cov=secure_semantic_docs --cov-report=term-missing
```

Integration tests require a local Spark session, started automatically by the
test fixture.

---

## Project structure

```
.
├── src/
│   └── secure_semantic_docs/
│       ├── core/               Settings, logging, Spark session factory,
│       │                       partition helpers, project metadata
│       ├── embeddings/         SentenceTransformer model loading, worker
│       │                       environment setup, partition-level encoding,
│       │                       cache reuse, vector serialisation (NumPy ↔ bytes)
│       ├── loader/             YAML config loader and builder
│       ├── models/             Frozen dataclasses: Config, SparkConfig,
│       │                       IcebergConfig, ChunkingConfig, EmbeddingConfig,
│       │                       SensitivityResult, readers, writers
│       ├── processing/         Text cleaning, word-boundary chunking,
│       │                       chunk enrichment, transient chunk text lookup
│       ├── security/           PyNaCl encryption (SecretBox), OS-keyring key
│       │                       management, sensitivity detection, chunk-field
│       │                       encryption helpers
│       ├── storage/            DDL-based schema loader (bronze, silver, gold)
│       ├── io/                 SparkReader / SparkWriter abstractions
│       ├── resources/          Bundled YAML configs, DDL files, synthetic data
│       ├── bronze_ingestion.py Bronze pipeline entry point
│       ├── silver_ingestion.py Silver pipeline entry point
│       └── gold_ingestion.py   One-pass chunk metadata + embeddings entry point
├── tests/
│   ├── unit/                   Fast, infrastructure-free unit tests
│   └── integration/            Tests requiring a live SparkSession
├── docker/                     Dockerfiles and docker-compose files
└── pyproject.toml
```

---

## Sensitivity detection

The silver pipeline tags every chunk with:

| Field                        | Type      | Description                                          |
|------------------------------|-----------|------------------------------------------------------|
| `sensitivity_score`          | `float`   | 0.0 (public) to 1.0 (restricted + many PII patterns) |
| `detected_sensitive_types`   | `list`    | e.g. `["email", "keyword:credential"]`               |
| `requires_encryption`        | `boolean` | `true` when score >= 0.5                             |
| `requires_restricted_access` | `boolean` | `true` when score >= 0.7                             |

Detection is a demo-level simulation using compiled regex patterns and a keyword
alternation regex. It is not a production PII engine.

Results are returned as a `SensitivityResult` frozen dataclass defined in `models/`.
The `security/sensitive_detector.py` module handles detection; `security/chunk_field_encryptor.py`
applies field-level PyNaCl encryption to chunks that have `requires_encryption=True`.

---

## Embedding design notes

- **No persisted chunk text** — Chunk plaintext is available only as a transient
  Spark workset column. `silver_chunks` stores spans, sensitivity flags, and
  permission metadata, but not raw chunk text. If embedding generation needs to
  reconstruct text, it reads source words through `processing/chunk_texts.py`
  using `source_path` and `chunk_span`.

- **Encrypted at rest** — The gold layer stores only ciphertext. Each float32
  embedding vector is serialised to raw bytes and encrypted with PyNaCl
  `SecretBox` (XSalsa20-Poly1305) before Parquet write. Plaintext vectors are
  never persisted.

- **Cache before inference** — `embeddings/vector_cache.py` loads the internal
  encrypted embedding cache, filters it by model, dimension, and key id, then
  splits chunks into hits and misses. Hits are converted by `embeddings/cache_rows.py`;
  misses go through `embeddings/encoder.py` and `embeddings/row_encoder.py`.

- **Model caching** — `_MODEL_CACHE` in `model_loader.py` stores one model
  instance per `(model_name, device)` key per worker process. Combined with
  `spark.python.worker.reuse=true`, each worker loads the model exactly once
  regardless of how many partitions it processes.

- **MPS / Apple Silicon** — MPS is subprocess-unsafe (Metal holds OS-level
  resources tied to the parent process). `worker_safe_device()` silently
  remaps `"mps"` → `"cpu"` inside every Spark worker, while the driver logs
  the resolved device correctly for observability.

- **Partition count** — For CPU-intensive workloads, the Spark best practice
  is 1 partition per core, not 2–4× (which is for IO/shuffle jobs). In local
  mode the count is always 1: multiple workers would each load the full model,
  causing OOM.

- **Null filtering** — Rows without `chunk_span` are dropped before cache lookup
  and repartitioning so executors do not spend time on rows that cannot be
  embedded.

- **`key_id`** — A UUID generated alongside the secret key and stored in
  the OS keyring. It is safe to log and store in every gold row.
  Recording which key encrypted which row enables future key rotation without
  re-encrypting all rows immediately.

---

## Security model

### Classification

Classification is metadata-driven and uses the fields already present in
silver: `allowed_roles`, `classification` (public / internal / confidential /
restricted), `department`, and `source_path`. No LLM classification is
required.

### Key management (local development)

For local development the secret key is stored in the **OS credential store**
via the `keyring` library (macOS Keychain, Windows Credential Manager, Linux
Secret Service / KWallet). The service name is `"secure-semantic-docs"` with
two entries: `"embedding-key"` (base64-encoded key) and `"embedding-key-id"`
(UUID). No key material is written to the filesystem.

In production, inject the key via the `DOCSEC_SECRET_KEY` environment variable
and manage rotation with a dedicated KMS (AWS KMS, HashiCorp Vault, etc.).

### Gold schema

| Column                                                           | Type            | Description                                |
|------------------------------------------------------------------|-----------------|--------------------------------------------|
| `embedding_id`                                                   | STRING          | UUID per embedding                         |
| `chunk_id`                                                       | STRING          | FK → silver.chunks                         |
| `document_id`                                                    | STRING          | FK → bronze.documents                      |
| `embedding_ciphertext`                                           | BINARY          | XSalsa20-Poly1305 authenticated ciphertext |
| `embedding_nonce`                                                | BINARY          | 24-byte random nonce                       |
| `embedding_algorithm`                                            | STRING          | `XSalsa20-Poly1305`                        |
| `embedding_dim`                                                  | INT             | Vector dimensionality                      |
| `embedding_dtype`                                                | STRING          | `float32`                                  |
| `embedding_model`                                                | STRING          | HuggingFace model identifier               |
| `key_id`                                                         | STRING          | Encryption key identifier                  |
| `classification`                                                 | STRING          | Sensitivity label                          |
| `allowed_roles`                                                  | ARRAY\<STRING\> | Roles permitted to decrypt                 |
| `owner`, `department`, `source_path`, `version`, `document_hash` | STRING          | Provenance                                 |
| `created_at`                                                     | STRING          | ISO-8601 timestamp                         |

---

## License

MIT. See [LICENSE](LICENSE) for details.

---

Secure Documents v0.4.0 -- [AnthonyWainer](mailto:awainerc@gmail.com)
