# AGENTS.md

## Purpose

This repository uses `AGENTS.md` to define implementation standards for Codex and similar coding agents. Follow these
instructions for every code change unless the user explicitly asks otherwise.
---

## Engineering Standards

- Prefer small, focused changes over broad refactors.
- Keep responsibilities isolated. Split unrelated behavior into separate functions, classes, or modules.
- Isolate ingestion, parsing, transformation, embedding, storage, and API concerns into separate layers.
- Keep side effects at the edges of the system.
- Preserve existing public APIs unless the user asks for a breaking change.
- Favor readability and maintainability over cleverness.
- Remove duplication when it improves clarity, but do not merge unrelated concerns.
- Raise explicit, meaningful exceptions instead of failing implicitly.
- Avoid hardcoded environment-specific paths, usernames, or machine-specific values.
- Prefer configuration through arguments, environment variables, or config files.
- Reuse existing utilities when they fit; do not duplicate logic across modules.

---

## Python Style

### General

- Follow PEP 8.
- Before committing, run `ruff check --fix` to auto-fix lint violations:
  ```bash
  ruff check --fix .
  ```
  Do **not** run `ruff format` — it unconditionally adds trailing commas before closing brackets, which violates this
  project's style.
  Ruff is PEP 8-compliant and replaces `isort` and `flake8` in a single tool.
- Never submit code that fails `ruff check .`.
- Use clear, descriptive names for functions, variables, classes, and modules.
- Keep functions short and single-purpose when practical.
- Avoid deeply nested control flow; prefer guard clauses and helper functions.
- Do not add unnecessary comments. Comments should explain intent or non-obvious constraints.
- Prefer immutable dataclasses or simple value objects for configuration-style data.
- Use docstrings for public functions, classes, and modules when behavior is not obvious.
- Apply formatting rules consistently across source code and configuration files such as `pyproject.toml`, YAML, JSON,
  and similar structured files.

### Type Hints

- Add type hints for all new or modified Python code.
- Annotate return types on all public functions, not just parameters.
- Prefer `X | Y` union syntax over `Optional[X]` or `Union[X, Y]`.
- Use `Protocol` for structural typing when you need duck-typed interfaces without inheritance.
- Use `TypeAlias` for complex repeated type expressions.

### Imports

- Do not leave unused imports, unused local variables, or dead helper code in the final change.
- If an import is no longer needed after a refactor, remove it before finishing.
- Pay special attention to test files, where temporary imports are easy to leave behind.
- Before finishing a change, scan newly added code for unused imports.

### Line Formatting

- Do not use backslashes (`\`) for line continuation. Use parentheses, brackets, or braces instead.
- When a statement or method chain spans multiple lines, wrap it with parentheses and place each chained call on its
  own line:
  ```python
  # Prefer
  result = (
      df
      .select("id", "content")
      .where("content is not null")
  )

  # Avoid — backslash continuation
  result = df.select("id", "content") \
      .where("content is not null")

  # Avoid — everything on one line
  result = df.select("id", "content").where("content is not null").orderBy("id")
  ```

### Trailing Commas

- Do not add a trailing comma before a closing `)`, `]`, or `}` unless the user explicitly asks for that style.
- This rule applies to function calls, method calls, function definitions, class constructors, decorators, `pytest`
  assertions, tuples, lists, dicts, sets, and structured config files such as TOML and JSON.
  ```python
  # Prefer
  def build_config(
      host: str,
      port: int
  ) -> dict[str, str]:
      return {
          "host": host,
          "port": str(port)
      }

  # Avoid
  def build_config(
      host: str,
      port: int,
  ) -> dict[str, str]:
      return {
          "host": host,
          "port": str(port),
      }
  ```
- Do not add trailing commas in inline `dict` or `list` literals.
  Prefer `{"a": 1}` over `{"a": 1,}` and `[1, 2]` over `[1, 2,]`.
- In multiline literals, apply the same rule: no trailing comma on the last item before the closing bracket.

---

## Error Handling

- Define custom exception types in a dedicated `exceptions.py` module when a module has distinct failure modes.
- Do not catch broad `Exception` without re-raising or converting it to a more specific type.
- Never swallow exceptions silently. At minimum, log the error before suppressing it.
- Prefer letting exceptions propagate to the caller rather than masking them with fallback values when the failure is
  unexpected.

---

## Logging

- Use the standard `logging` module. Never use `print()` for diagnostic output in library or pipeline code.
- Use the appropriate level: `DEBUG` for detailed diagnostics, `INFO` for progress milestones, `WARNING` for
  recoverable anomalies, `ERROR` for failures.
- Never log sensitive data such as credentials, tokens, document content, PII, or encryption keys.
- Use structured log messages with relevant context rather than bare string concatenation.

---

## Security and Compliance

### Credentials

- Never hardcode credentials, connection strings, API keys, or secrets in source code or committed config files.
  This includes `.env` files and YAML configs that are tracked by git.
- For local development, retrieve secrets using the `keyring` library so they are stored in the OS credential store
  rather than in files:
  ```python
  import keyring

  password = keyring.get_password("secure-semantic-docs", "db-user")
  ```
- For deployed environments, inject secrets via environment variables or a secrets manager at runtime.

### Encryption (PyNaCl)

- Use `PyNaCl` for all encryption and signing operations. Do not implement custom cryptographic primitives.
- Encrypt sensitive document content and metadata before writing to any storage layer. Decrypt only at the point of
  consumption and only for authorized roles.
- Use `nacl.secret.SecretBox` for symmetric encryption of document content and chunk payloads.
- Use `nacl.public.Box` for asymmetric encryption when exchanging data between components with different key pairs.
- Never store raw private keys or secret keys in code, config files, or environment variables in plain text. Wrap them
  with a key derivation function (`nacl.pwhash`) or retrieve from a key vault.
- Rotate encryption keys according to the project's key management policy.
- Do not log encryption keys, nonces, or ciphertext in human-readable form.

### GDPR / RGPD

- Treat any document content that may contain personal data as sensitive by default.
- Apply sensitive-information detection during the processing layer before writing to the silver or gold tables.
- Ensure that deletion requests can be honoured: design storage such that records for a given user or document can
  be purged without breaking referential integrity across layers.
- Do not replicate personal data across layers beyond what is necessary for the pipeline to function.
- Document data retention periods and enforce them through scheduled maintenance jobs, not ad hoc deletes.

---

## Docker

### Layer Caching — Cache What Changes Least First

The single most impactful Dockerfile optimization is ordering instructions so that layers that rarely change come
before layers that change often. Docker reuses a cached layer as long as none of the preceding layers have changed.

- **Always copy dependency manifests before copying source code.** Install dependencies in a dedicated layer, then
  copy the application code. This way a source-only change does not invalidate the dependency install cache:
  ```dockerfile
  # Prefer — dependency install cached independently of source changes (build: ~30 sec on re-runs)
  COPY requirements.txt /app/
  RUN pip install --no-cache-dir -r requirements.txt
  COPY . /app

  # Avoid — every source change invalidates the pip install layer (build: 5-10 min every time)
  COPY . /app
  RUN pip install --no-cache-dir -r requirements.txt
  ```
- Apply the same principle to any package manifest: copy `pyproject.toml` and lock files first, install, then copy
  the rest of the source tree.
- Order `RUN` instructions from least-changing (system packages, base tools) to most-changing (app dependencies,
  source code).

### Base Images

- Use slim or distroless base images. Prefer `python:3.12-slim` over `python:3.12` to reduce image size and attack
  surface.
- Pin base image versions including the patch tag (e.g. `python:3.12.4-slim`) to ensure reproducible builds.
- Do not use `latest` as a base image tag in production Dockerfiles.

### Multi-Stage Builds

- Use multi-stage builds to separate build-time dependencies from the final runtime image:
  ```dockerfile
  # Build stage — includes compilers, dev headers, etc.
  FROM python:3.12-slim AS builder
  COPY requirements.txt .
  RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

  # Runtime stage — only the installed packages, no build tools
  FROM python:3.12-slim
  COPY --from=builder /install /usr/local
  COPY src/ /app/src/
  ```
- Never install build-only tools (compilers, `gcc`, `curl`, test runners) in the final stage.

### Security

- Never embed secrets, credentials, API keys, or `.env` files into a Docker image or pass them as `ARG` values
  (they appear in image history). Inject them as environment variables at container runtime or via a secrets manager.
- Do not run containers as `root`. Create a non-root user and switch to it before the entrypoint:
  ```dockerfile
  RUN adduser --disabled-password --gecos "" appuser
  USER appuser
  ```
- Scan images for vulnerabilities with `docker scout` or equivalent before pushing to a registry.

### Build Context

- Always include a `.dockerignore` file. At minimum exclude:
  ```
  .git
  .venv
  __pycache__
  *.pyc
  *.egg-info
  .env
  local.settings.json
  tests/
  docker/
  *.md
  ```
- A large build context slows every build even when layer caching hits. Keep it minimal.

### General

- Expose services on explicit, documented ports. Do not use host networking unless strictly necessary.
- Use `CMD` for the default runtime command and `ENTRYPOINT` for a fixed executable. Do not mix their roles.
- Prefer `COPY` over `ADD` unless you specifically need URL fetching or automatic tar extraction.
- Chain `RUN` commands that belong to the same logical step with `&&` and clean up in the same layer:
  ```dockerfile
  RUN apt-get update \
      && apt-get install -y --no-install-recommends libgomp1 \
      && rm -rf /var/lib/apt/lists/*
  ```
- Document all required environment variables in a `.env.example` file committed to the repository (no real values).
- Use `docker compose` for local multi-service development (Chroma server, OpenMetadata, Spark, etc.). Keep compose
  files under `docker/`.

---

## PySpark Best Practices

### PySpark Imports

- Do not alias `pyspark.sql.functions` as `F`. Import only the specific functions you need:
  ```python
  # Prefer
  from pyspark.sql.functions import col, isnotnull, coalesce, regexp_replace

  # Avoid
  import pyspark.sql.functions as F
  # ... F.col(...), F.coalesce(...), etc.
  ```
- The `F.` alias obscures which functions are used, complicates static analysis, and pollutes the namespace.

### General

- Keep DataFrame transformations declarative and chain operations in a readable way.
- Prefer built-in Spark functions over Python UDFs whenever possible.
- Avoid Python UDFs unless there is no viable native Spark alternative. When a UDF truly cannot be avoided, prefer
  `rdd.mapPartitions(...)` or `DataFrame.mapInPandas(...)` over a row-by-row UDF to reduce serialization overhead
  and avoid saturating the driver with per-row Python callbacks:
  ```python
  # Prefer — partition-level processing
  def process_partition(rows):
      for row in rows:
          yield transform(row)

  result_rdd = input_df.rdd.mapPartitions(process_partition)

  # Avoid — row-by-row UDF
  ```
- Isolate Spark I/O, schema handling, parsing, and business transformations into separate functions or modules.
- Avoid unnecessary conversions between DataFrames, RDDs, and Python objects.
- Keep transformations composable: one function should do one logical step and return a DataFrame.
- Keep write logic separate from transformation logic.
- Do not hardcode environment-specific table names, paths, or workspace values inside transformation logic.
- Add tests for pure transformation logic and parser logic even when full Spark integration tests are not practical.
- When code must split across lines, prefer parenthesized multi-line DataFrame chains:
  ```python
  from pyspark.sql.functions import col

  output_df = (
      input_df
      .select("doc_id", "content", "permissions")
      .where(col("content").isNotNull())
  )
  ```

### DataFrame Operations

- Avoid repetitive `.withColumn(...)` or `.withColumnRenamed(...)` chains when a single `.select(...)` can express the
  result more clearly.
- Avoid multiple sequential `.filter(...)` calls when conditions can be combined into a single filter expression.
- Do not read all columns from a table or file source unless actually needed.
- Do not filter dates as strings. Convert to `DateType` or `TimestampType` before comparison.
- Use meaningful column aliases after complex expressions to make the output schema self-documenting.
- Prefer native conditional helpers (`coalesce`, `nvl`, `nvl2`) when they express logic more clearly than long
  `when(...).otherwise(...)` chains.

### Joins

- After joins, avoid ambiguous columns. Use `.alias(...)` on both sides and qualify columns explicitly.
- Avoid `right` joins. Prefer reversing the join order and using a `left` join instead.
- Filter each DataFrame before joining.
- Prefer `broadcast(small_df)` from `pyspark.sql.functions` for genuinely small lookup DataFrames.
- Do not use `collect()` to build Python lists for `.isin(...)`. Keep the logic distributed with DataFrame joins.
- When joining many DataFrames, apply `inner` joins before outer joins when that reduces data volume.

### Driver Safety

- Avoid collecting data to the driver unless the dataset is known to be small and bounded.
- Do not use `.count()` just to check whether a DataFrame is empty. Prefer `.isEmpty()`.
- Do not use `collect()` for large datasets. Prefer `foreachPartition(...)`, `mapPartitions(...)`, or distributed
  writes.
- Avoid repeated Spark actions (`show()`, `count()`, `collect()`) in production code.

### Performance and Caching

- Cache or persist a DataFrame when it is reused multiple times in the same job. Call `.unpersist()` when no longer
  needed to free executor memory.
- Avoid repartitioning without controlling the number of partitions. Specify a count appropriate to the data volume.
- Be mindful of small-file output problems. Target reasonable file sizes when designing output partitions.
- Tune `spark.sql.shuffle.partitions` at job startup rather than accepting the default 200.

### Schema Management

- Declare schemas explicitly using `StructType` rather than relying on inference for production file sources.
- Validate incoming data schemas before writing to any Iceberg table when schema changes are not expected.

---

## SentenceTransformers (Embedding Generation)

- Isolate embedding generation into a dedicated module (e.g. `embeddings/`). Do not mix it with chunking or storage
  logic.
- Load the model once per job or process. Never reload it inside a loop or per-record function.
- Use `mapPartitions` or `mapInPandas` to run embedding inference on Spark executors partition-by-partition, keeping
  model loading inside the partition function:
  ```python
  def embed_partition(rows):
      from sentence_transformers import SentenceTransformer
      model = SentenceTransformer("all-MiniLM-L6-v2")
      for row in rows:
          vector = model.encode(row["chunk_text"]).tolist()
          yield (row["chunk_id"], vector)
  ```
- Pin the model name and version in configuration, not inside transformation code.
- Do not store raw model weights or large binary artifacts in the repository; reference them by name and download at
  runtime or build time.
- Normalize embeddings (`normalize_embeddings=True`) when the downstream vector store uses cosine similarity.
- Validate embedding dimensionality against the expected schema before writing to the gold layer or Chroma.

---

## Apache Iceberg (Lakehouse)

### Medallion Architecture

- Maintain three layers: **bronze** (raw ingested documents), **silver** (cleaned and chunked text), **gold**
  (enriched chunks with embeddings and permission metadata).
- Bronze tables store the original document bytes or text with minimal transformation. Do not apply business logic in
  the bronze layer.
- Silver tables contain cleaned text, normalized metadata, detected sensitive fields, and chunked content. No
  embeddings at this layer.
- Gold tables contain the final chunk records with embedding vectors, permission tags, classification labels, and
  audit fields ready for serving.
- Never write directly to a downstream layer without passing through the preceding one.

### General Iceberg Rules

- Use `MERGE INTO` for upserts instead of full overwrites when only a subset of rows changes.
- Do not use `overwriteSchema=True` unless a schema change is intentional and has been reviewed.
- Do not rely on auto schema evolution to silently absorb breaking changes. Validate the incoming schema before
  writing.
- Run `OPTIMIZE` and `VACUUM` as scheduled maintenance operations; do not embed them in per-batch code paths.
- Use partition pruning-friendly predicates. Design partition schemes around the columns most commonly used in queries
  (e.g. ingestion date, document type).
- Prefer `replaceWhere` over full table overwrites when reprocessing a bounded partition or date range.
- Set appropriate `write.metadata.metrics-mode` to control metadata collection costs.

---

## Chroma (Vector Store)

- Isolate all Chroma client code in a dedicated module (e.g. `vector_store/`). Do not call Chroma directly from
  transformation or ingestion code.
- Use a persistent Chroma client for production; never use the in-memory client in deployed code.
- Name collections consistently and document the naming convention. Collection names must encode the layer or model
  version when multiple embedding spaces coexist.
- Always pass `ids` explicitly when upserting documents. Do not rely on auto-generated IDs for records that need to
  be updated or deleted later.
- Store permission metadata alongside each embedding as Chroma document metadata. Use it to filter results at query
  time rather than post-filtering in Python.
- Validate that the embedding dimensionality of new documents matches the collection's existing dimensionality before
  upserting.
- Do not store raw document text or PII in Chroma metadata fields unless the data has been sanitized and the
  collection is access-controlled.

---

## OpenMetadata (Governance and Catalogue)

- Register every Iceberg table (bronze, silver, gold) and every Chroma collection in the OpenMetadata catalogue.
- Record lineage edges: data source → bronze → silver → gold → Chroma. Keep lineage up to date when pipelines change.
- Apply classification tags (`PII`, `Sensitive`, `Public`, etc.) to columns and tables during the processing step.
  Do not leave classification as a manual post-hoc activity.
- Use OpenMetadata's data quality framework to define and run expectations on bronze and silver tables after each
  ingestion run.
- Use the OpenMetadata API client inside pipeline code to push metadata programmatically. Do not rely solely on the
  UI for catalogue updates in automated jobs.
- Keep OpenMetadata service connection credentials in a secrets manager. Do not hardcode them in pipeline scripts.

---

## Testing

- Add or update `pytest` tests for every behavior change or new feature.
- Prefer focused unit tests over broad integration tests unless integration coverage is necessary.
- Test success cases, edge cases, and failure paths.
- Use `tmp_path`, `monkeypatch`, and fixtures where appropriate.
- Keep tests deterministic. Avoid real network calls, wall-clock timing dependencies, and machine-specific assumptions.
- For bug fixes, add a regression test that fails before the fix and passes after it.
- Mock Chroma, OpenMetadata, and external model calls in unit tests. Use real clients only in integration tests.
- Mark tests that require external infrastructure (Spark, Chroma server, OpenMetadata) with appropriate pytest markers
  so they can be excluded from fast local runs.
- Test encryption and decryption round-trips for any component that uses PyNaCl.
- Test that permission metadata is correctly propagated from ingestion through to the gold layer and Chroma.

---

## Project Structure

```
src/
  ingestion/        # PySpark readers and parsers (bronze layer)
  processing/       # Text cleaning, chunking, metadata enrichment, PII detection
  embeddings/       # SentenceTransformers model loading and embedding generation
  vector_store/     # Chroma client wrapper
  lakehouse/        # Iceberg read/write helpers (bronze / silver / gold)
  governance/       # OpenMetadata API client and lineage registration
  security/         # PyNaCl encryption/decryption utilities, permission enforcement
  api/              # Serving layer (semantic search, role-based query endpoints)
  config.py         # Centralised configuration loading
tests/              # Mirrors src/ layout
docker/             # Dockerfiles and docker-compose files
```

- Keep source code under `src/`.
- Keep tests under `tests/`, mirroring the source layout.
- Keep Docker files under `docker/`.
- Avoid committing generated artifacts such as `__pycache__`, `.pyc`, `.venv`, coverage output, or build metadata.

---

## Dependency and Tooling Guidelines

- Use `pyproject.toml` as the authoritative source for project metadata and dependencies.
- Keep runtime dependencies separate from development and test dependencies.
- Pin versions for cryptographic libraries (`PyNaCl`) and model libraries (`sentence-transformers`) to ensure
  reproducible behaviour.
- Update documentation when behavior, configuration, or developer workflows change.

---

## Change Validation

- Run the smallest relevant test scope first, then broader validation if needed.
- If tests cannot be run, state that clearly and explain why.
- When modifying configuration or packaging behavior, verify the documented workflow still matches the code.
- Before finishing any change, scan for:
    - Unused imports and trailing commas before closing brackets.
    - Hardcoded secrets, credentials, or paths.
    - Missing type hints on new public functions.
    - Unencrypted writes of sensitive fields to any storage layer.
    - Missing lineage or catalogue registration when new tables or collections are created.
