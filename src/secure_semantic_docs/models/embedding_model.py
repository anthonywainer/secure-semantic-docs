from dataclasses import dataclass


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
