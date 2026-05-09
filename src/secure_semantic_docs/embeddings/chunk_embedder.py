"""Partition-level embedding encoder and Spark DataFrame builder.

Public API
----------
generate_embeddings(spark, silver_df, config)
    Transform a silver-layer DataFrame into a gold-layer DataFrame by adding
    embedding vectors to every chunk.  This is the only function consumers
    should call; everything else is an implementation detail.

Performance design
------------------
Spark parallelism
    Embedding is CPU-intensive: each partition runs a full model forward pass
    that saturates one core.  The Spark best practice for CPU-bound workloads
    is **1 partition per available core** — unlike shuffle-heavy IO jobs where
    2–4× over-partitioning hides straggler tasks.
    ``defaultParallelism = N_executors × cores_per_executor`` in cluster mode,
    so using it directly gives exactly one partition task per core.
    Manual override is available via ``embedding.num_partitions`` in the YAML.

    In local mode (``spark.master`` starts with ``"local"``), the partition
    count is capped to 1 regardless of core count.  ``local[*]`` spawns one
    Python worker process per core; each would load the full model into memory
    simultaneously causing OOM crashes.  One partition on a single machine is
    optimal because the model's internal batching already saturates the CPU.

Null filtering
    Rows with a null or empty ``chunk_text`` are dropped before repartition.
    They would produce meaningless near-zero vectors and waste executor compute.

Batch encoding
    All rows in a partition are collected into a Python list and encoded in a
    single ``model.encode(texts)`` call.  This saturates the GPU/CPU matrix
    pipeline and avoids the per-row overhead of DataLoader setup.  Partition
    memory is bounded by Spark's configured memory per executor.

Model caching
    The model is loaded once per worker process via :func:`load_cached_model`.
    When Spark reuses workers (the default), subsequent partitions handled by
    the same worker skip model loading entirely.

Primitive closure
    The lambda passed to ``mapPartitions`` captures only plain Python scalars
    (``str``, ``int``, ``bool``) — not Config objects, Path instances, or
    any dataclass.  Spark must pickle this closure and ship it to executors;
    complex objects are unreliable across Python versions and JVM boundaries.

Schema broadcast
    The gold schema is resolved once on the driver (calling ``load_schema``)
    and passed directly to ``createDataFrame``.  Workers never touch the
    filesystem for the schema.

Embedding dimensionality
    Dimension validation (comparing actual vector length against
    ``EmbeddingConfig.dim``) is intentionally omitted from this module.
    Calling ``limit(1).collect()`` would trigger a full Spark action —
    materialising the RDD across all executors just to inspect one vector —
    which defeats the lazy evaluation model and adds one full job per pipeline
    run.  Instead, pin ``EmbeddingConfig.dim`` to match the chosen model and
    enforce it via an integration test or a data-quality expectation registered
    in OpenMetadata against the gold table.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime

from pyspark.sql import DataFrame, Row, SparkSession
from pyspark.sql.functions import col, isnotnull
from pyspark.sql.types import StructType

from secure_semantic_docs.core import BaseSettings
from secure_semantic_docs.core.exceptions import EmbeddingError
from secure_semantic_docs.embeddings.model_loader import load_cached_model, resolve_device
from secure_semantic_docs.embeddings.worker_env import configure_worker_environment, worker_safe_device
from secure_semantic_docs.loader import load_config
from secure_semantic_docs.models import Config
from secure_semantic_docs.storage.schemas import load_schema

logger = logging.getLogger(BaseSettings.APP_NAME)

# Type alias for one gold layer output row (matches gold_embeddings.ddl column order).
GoldRow = tuple[
    str,  # chunk_id
    str,  # document_id
    list[float],  # embedding
    str,  # embedding_model
    str,  # embedding_created_at
    str | None,  # classification
    list | None,  # allowed_roles
    str | None,  # owner
    str | None,  # department
    float,  # sensitivity_score
    str | None,  # source_path
    str | None,  # version
    str | None,  # document_hash
]


def _resolve_embedding_partitions(
        total_executor_cores: int,
        configured: int,
        is_local_mode: bool
) -> int:
    """Return the number of Spark partitions to use for the embedding step.

    Spark best practice for CPU-bound workloads is 1 partition per core.
    Unlike shuffle-heavy IO jobs (where 2–4× over-partitioning hides straggler
    tasks), embedding inference already saturates one core per partition through
    the model's internal batch parallelism — adding more partitions only
    introduces scheduling overhead.

    Parameters
    ----------
    total_executor_cores:
        ``spark.sparkContext.defaultParallelism`` — equals
        ``N_executors × cores_per_executor`` in cluster mode, or the thread
        count in local mode.
    configured:
        ``EmbeddingConfig.num_partitions`` from the YAML.  When ``> 0`` it
        takes precedence over the auto-calculated value (useful for tuning
        on skewed datasets or unusually large/small clusters).
    is_local_mode:
        Whether the SparkSession is running locally (master starts with
        ``"local"``).  In local mode the result is always 1: each "core"
        would launch a separate Python worker process that loads the full
        model into memory simultaneously — causing OOM crashes.  One partition
        is safe and optimal because the model's batching already uses all cores.

    Returns
    -------
    int
        Partition count, always ``>= 1``.
    """
    if is_local_mode:
        return 1
    if configured > 0:
        return configured
    return max(1, total_executor_cores)


def embed_partition(
        rows: Iterator[Row],
        model_name: str,
        device: str,
        batch_size: int,
        normalize: bool,
        created_at: str
) -> Iterator[GoldRow]:
    """Embed all chunks in one Spark partition.

    Called inside each executor process.  All parameters are plain Python
    scalars so the closure is safely picklable across the driver / executor
    boundary.  ``configure_worker_environment`` is called first to set the
    necessary env vars before any ``sentence_transformers`` import.  The full
    partition is materialised into a list so all chunk texts can be encoded in a
    single batched ``sentence_transformer.encode`` call; partition memory is bounded by
    Spark's configured memory per executor.

    Parameters
    ----------
    rows:
        Partition iterator provided by ``mapPartitions``.
    model_name:
        HuggingFace model identifier.
    device:
        Concrete device string (``"cpu"``, ``"cuda"``, ``"mps"``).
        Pass the resolved value from :func:`resolve_device`; do not pass
        ``"auto"`` here.
    batch_size:
        Texts per forward pass.
    normalize:
        Whether to L2-normalise output vectors.
    created_at:
        ISO-8601 timestamp string to stamp on every output row.
    """
    configure_worker_environment()
    sentence_transformer = load_cached_model(model_name, worker_safe_device(device))

    chunk_rows = [chunk_row.asDict() for chunk_row in rows]
    if not chunk_rows:
        return

    chunk_texts = [str(chunk_fields.get("chunk_text", "") or "") for chunk_fields in chunk_rows]

    try:
        embedding_vectors: list[list[float]] = sentence_transformer.encode(
            chunk_texts,
            normalize_embeddings=normalize,
            show_progress_bar=False,
            batch_size=batch_size
        ).tolist()
    except Exception as exc:
        raise EmbeddingError(
            f"Batch encode failed -- model={model_name} "
            f"partition_size={len(chunk_texts)}: {exc}"
        ) from exc

    for chunk_fields, embedding_vector in zip(chunk_rows, embedding_vectors, strict=True):
        yield (
            str(chunk_fields["chunk_id"]),
            str(chunk_fields["document_id"]),
            embedding_vector,
            model_name,
            created_at,
            chunk_fields.get("classification"),
            chunk_fields.get("allowed_roles"),
            chunk_fields.get("owner"),
            chunk_fields.get("department"),
            float(chunk_fields.get("sensitivity_score", 0.0) or 0.0),
            chunk_fields.get("source_path"),
            chunk_fields.get("version"),
            chunk_fields.get("document_hash")
        )


def generate_embeddings(
        spark: SparkSession,
        silver_df: DataFrame,
        config: Config | None = None
) -> DataFrame:
    """Generate embedding vectors for every silver chunk and return a gold DataFrame.

    Scalars are resolved on the driver so the ``mapPartitions`` closure
    captures only primitives.  Null/empty ``chunk_text`` rows are filtered
    before repartition.  The schema is loaded once on the driver and broadcast
    to ``createDataFrame``.  See the module docstring for the full performance
    design.

    Parameters
    ----------
    spark:
        Active :class:`~pyspark.sql.SparkSession`.
    silver_df:
        Silver-layer DataFrame with at least ``chunk_id``, ``document_id``,
        and ``chunk_text`` columns.
    config:
        Optional configuration.  Loaded from YAML if *None*.

    Returns
    -------
    DataFrame
        Gold-layer DataFrame conforming to ``gold_embeddings.ddl``.
    """
    pipeline_config = config or load_config()
    embedding_cfg = pipeline_config.embedding

    model_name: str = embedding_cfg.model
    device: str = resolve_device(embedding_cfg.device)
    batch_size: int = embedding_cfg.batch_size
    normalize: bool = embedding_cfg.normalize
    created_at: str = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    gold_schema: StructType = load_schema("gold_embeddings")

    non_empty_chunks_df = silver_df.filter(
        isnotnull(col("chunk_text")) & (col("chunk_text") != "")
    )

    spark_master: str = spark.sparkContext.master
    is_local_mode: bool = spark_master.startswith("local")
    num_partitions: int = _resolve_embedding_partitions(
        total_executor_cores=spark.sparkContext.defaultParallelism,
        configured=embedding_cfg.num_partitions,
        is_local_mode=is_local_mode
    )

    logger.info(
        "Generating embeddings -- model=%s device=%s batch_size=%d partitions=%d local=%s",
        model_name,
        device,
        batch_size,
        num_partitions,
        is_local_mode
    )

    balanced_chunks_df = non_empty_chunks_df.repartition(num_partitions)

    gold_chunks_rdd = balanced_chunks_df.rdd.mapPartitions(
        lambda partition_rows: embed_partition(
            partition_rows, model_name, device, batch_size, normalize, created_at
        )
    )
    return spark.createDataFrame(gold_chunks_rdd, schema=gold_schema)
