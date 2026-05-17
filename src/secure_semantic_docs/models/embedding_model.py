from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pyspark.sql import SparkSession

from secure_semantic_docs.core.spark_partitions import compute_partition_count


@dataclass(frozen=True)
class EmbeddingConfig:
    """Embedding model settings.

    Attributes
    ----------
    model:
        HuggingFace model name passed to :class:`sentence_transformers.SentenceTransformer`.
    dim:
        Output embedding dimensionality. Must match the chosen model.
    batch_size:
        Number of texts encoded in a single forward pass. Larger values improve
        GPU throughput; reduce if OOM errors occur on cluster executors.
    device:
        Compute device for inference. ``"auto"`` detects CUDA first, then MPS,
        then falls back to CPU. Pass ``"cpu"``, ``"cuda"``, or ``"mps"`` to pin.
    num_partitions:
        Number of Spark partitions used during embedding. ``0`` means use
        ``spark.sparkContext.defaultParallelism`` (one partition per executor
        core), which is the right default for a cluster.
    normalize:
        Whether to L2-normalise the output vectors (required for cosine search).
    """

    model: str = "all-MiniLM-L6-v2"
    dim: int = 384
    batch_size: int = 64
    device: str = "auto"
    num_partitions: int = 0
    normalize: bool = True


class _ReaderEntries(Protocol):
    @property
    def entries(self) -> Mapping[str, Any]:
        """Configured reader entries keyed by reader name."""
        ...  # pragma: no cover


class _EmbeddingSettingsConfig(Protocol):
    @property
    def embedding(self) -> EmbeddingConfig:
        """Embedding configuration section."""
        ...  # pragma: no cover

    @property
    def readers(self) -> _ReaderEntries:
        """Reader configuration section."""
        ...  # pragma: no cover

    @property
    def raw_documents_dir(self) -> Path:
        """Directory containing raw documents."""
        ...  # pragma: no cover


@dataclass(frozen=True)
class EmbeddingSettings:
    """Primitive settings passed from the Spark driver to workers."""

    model_name: str
    device: str
    batch_size: int
    normalize: bool
    embedding_dim: int
    created_at: str
    raw_docs_dir: str
    num_partitions: int
    is_local_mode: bool
    encryption_key: bytes
    key_id: str


def resolve_embedding_settings(
        spark: SparkSession,
        config: _EmbeddingSettingsConfig
) -> EmbeddingSettings:
    """Resolve embedding settings from Spark and application config."""
    from secure_semantic_docs.embeddings.model_loader import resolve_device  # noqa: PLC0415

    embedding_cfg = config.embedding
    raw_docs_dir = _raw_documents_dir(config)

    spark_master = spark.sparkContext.master
    is_local_mode = spark_master.startswith('local')
    num_partitions = compute_partition_count(
        total_executor_cores=spark.sparkContext.defaultParallelism,
        configured=embedding_cfg.num_partitions,
        is_local_mode=is_local_mode
    )
    encryption_key, key_id = resolve_key_material(config)

    return EmbeddingSettings(
        model_name=embedding_cfg.model,
        device=resolve_device(embedding_cfg.device),
        batch_size=embedding_cfg.batch_size,
        normalize=embedding_cfg.normalize,
        embedding_dim=embedding_cfg.dim,
        created_at=datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
        raw_docs_dir=raw_docs_dir,
        num_partitions=num_partitions,
        is_local_mode=is_local_mode,
        encryption_key=encryption_key,
        key_id=key_id
    )


def _raw_documents_dir(config: _EmbeddingSettingsConfig) -> str:
    raw_docs_reader = config.readers.entries.get('raw_documents')
    if raw_docs_reader is None:
        return str(config.raw_documents_dir)

    options = getattr(raw_docs_reader, 'options', None)
    if isinstance(options, Mapping) and options.get('path') is not None:
        return str(options['path'])

    return str(config.raw_documents_dir)


def resolve_key_material(config: Any) -> tuple[bytes, str]:
    """Return key material without importing keyring during model import."""
    from secure_semantic_docs.security.keyring_store import \
        resolve_key_material as _resolve_key_material  # noqa: PLC0415

    return _resolve_key_material(config)
