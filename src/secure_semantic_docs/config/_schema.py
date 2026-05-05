"""Immutable configuration dataclasses for docsec."""

from dataclasses import dataclass, field
from pathlib import Path


def _project_root() -> Path:
    """Resolve the project root as the grandparent of the src/ directory."""
    return Path(__file__).resolve().parent.parent.parent.parent


# ---------------------------------------------------------------------------
# Sub-config: embedding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EmbeddingConfig:
    """Embedding model settings."""

    model: str = "all-MiniLM-L6-v2"
    dim: int = 384


# ---------------------------------------------------------------------------
# Sub-config: pipeline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineConfig:
    """Data pipeline settings."""

    chunk_size: int = 400
    chunk_overlap: int = 80
    default_top_k: int = 5
    retrieval_candidate_multiplier: int = 4


# ---------------------------------------------------------------------------
# Sub-config: storage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StorageConfig:
    """Storage and vector-store settings."""

    chroma_collection_name: str = "docsec_v1"


# ---------------------------------------------------------------------------
# Sub-config: security
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SecurityConfig:
    """Security and key-management settings."""

    secret_key_env_var: str = "DOCSEC_SECRET_KEY"


# ---------------------------------------------------------------------------
# Sub-config: iceberg
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IcebergConfig:
    """Apache Iceberg catalog and runtime settings.

    Disabled by default for local development (Parquet is used instead).
    Enabled in Docker / production via ``config.prod.yml`` when
    ``DOCSEC_ENV=prod``.

    Table layout
    ------------
    Each pipeline layer maps to its own Iceberg namespace (schema):

    ============  =========  ===========  ===================================
    Logical name  Namespace  Table        Full identifier
    ============  =========  ===========  ===================================
    bronze layer  bronze     documents    <catalog>.bronze.documents
    silver layer  silver     chunks       <catalog>.silver.chunks
    gold layer    gold       embeddings   <catalog>.gold.embeddings
    ============  =========  ===========  ===================================

    Namespaces are created with ``CREATE NAMESPACE IF NOT EXISTS`` before
    the first write so the catalog does not need to be pre-configured.

    catalog_type:
        ``"rest"``    -- Iceberg REST catalog (Docker production default).
        ``"hadoop"``  -- File-system Hadoop catalog (no extra service needed).

    spark_jars:
        Pre-downloaded local JAR path (Docker).  Takes precedence over
        ``spark_packages`` when non-empty.

    spark_packages:
        Maven coordinates for the Iceberg Spark runtime JAR.
        PySpark 3.5 / Scala 2.12: ``org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.6.1``
        PySpark 4.0+ / Scala 2.13: update to ``org.apache.iceberg:iceberg-spark-runtime-4.0_2.13:<version>``
        once Iceberg 1.7.0 (Spark 4.x support) is released.
    """

    enabled: bool = False
    catalog_name: str = "local"
    catalog_type: str = "rest"
    catalog_uri: str = "http://iceberg-rest:8181"
    warehouse: str = "/app/lakehouse/iceberg_warehouse"
    # Maven coordinates -- used for local dev / CI where internet is available.
    spark_packages: str = "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.6.1"
    # Pre-downloaded JAR path -- used in Docker where Maven is not available.
    # When non-empty this takes precedence over spark_packages.
    spark_jars: str = ""


# ---------------------------------------------------------------------------
# Sub-config: spark
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SparkConfig:
    """PySpark session settings."""

    app_name: str = "DocsecPipeline"
    master: str = "local[*]"
    shuffle_partitions: int = 4
    driver_memory: str = "2g"
    executor_memory: str = "1g"
    log_level: str = "WARN"


# ---------------------------------------------------------------------------
# Sub-config: readers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParquetReaderConfig:
    """Parquet DataFrameReader options."""

    merge_schema: bool = True
    path_glob_filter: str = "*.parquet"


@dataclass(frozen=True)
class JsonReaderConfig:
    """JSON DataFrameReader options."""

    multiline: bool = False
    encoding: str = "utf-8"
    allow_comments: bool = False
    allow_unquoted_field_names: bool = False


@dataclass(frozen=True)
class CsvReaderConfig:
    """CSV DataFrameReader options."""

    header: bool = True
    infer_schema: bool = True
    delimiter: str = ","
    encoding: str = "utf-8"
    quote: str = '"'
    escape: str = "\\"
    null_value: str = ""


@dataclass(frozen=True)
class ReadersConfig:
    """Bundled reader options for all supported formats."""

    parquet: ParquetReaderConfig = field(default_factory=ParquetReaderConfig)
    json: JsonReaderConfig = field(default_factory=JsonReaderConfig)
    csv: CsvReaderConfig = field(default_factory=CsvReaderConfig)


# ---------------------------------------------------------------------------
# Sub-config: writers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParquetWriterConfig:
    """Parquet DataFrameWriter options."""

    compression: str = "snappy"
    mode: str = "overwrite"
    partition_overwrite_mode: str = "dynamic"


@dataclass(frozen=True)
class JsonWriterConfig:
    """JSON DataFrameWriter options."""

    compression: str = "none"
    mode: str = "overwrite"
    date_format: str = "yyyy-MM-dd"
    timestamp_format: str = "yyyy-MM-dd'T'HH:mm:ss'Z'"


@dataclass(frozen=True)
class CsvWriterConfig:
    """CSV DataFrameWriter options."""

    header: bool = True
    compression: str = "none"
    mode: str = "overwrite"
    delimiter: str = ","
    quote: str = '"'
    escape: str = "\\"
    null_value: str = ""
    date_format: str = "yyyy-MM-dd"


@dataclass(frozen=True)
class WritersConfig:
    """Bundled writer options for all supported formats."""

    parquet: ParquetWriterConfig = field(default_factory=ParquetWriterConfig)
    json: JsonWriterConfig = field(default_factory=JsonWriterConfig)
    csv: CsvWriterConfig = field(default_factory=CsvWriterConfig)


# ---------------------------------------------------------------------------
# Root Config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    """Immutable project-wide configuration assembled from YAML files.

    Paths are derived from *project_root* so the project stays portable.
    Scalar convenience properties expose nested sub-config values so
    existing callers using ``config.chunk_size`` etc. continue to work.
    """

    project_root: Path = field(default_factory=_project_root)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    spark: SparkConfig = field(default_factory=SparkConfig)
    iceberg: IcebergConfig = field(default_factory=IcebergConfig)
    readers: ReadersConfig = field(default_factory=ReadersConfig)
    writers: WritersConfig = field(default_factory=WritersConfig)

    # --- Derived directory paths ---

    @property
    def data_dir(self) -> Path:
        """Return the data directory."""
        return self.project_root / "data"

    @property
    def raw_documents_dir(self) -> Path:
        """Return the raw documents directory."""
        return self.data_dir / "raw_documents"

    @property
    def metadata_dir(self) -> Path:
        """Return the generated metadata directory."""
        return self.data_dir / "metadata"

    @property
    def users_dir(self) -> Path:
        """Return the generated users directory."""
        return self.data_dir / "users"

    @property
    def lakehouse_dir(self) -> Path:
        """Return the lakehouse root directory."""
        return self.project_root / "lakehouse"

    @property
    def bronze_dir(self) -> Path:
        """Return the bronze layer directory."""
        return self.lakehouse_dir / "bronze_documents"

    @property
    def silver_dir(self) -> Path:
        """Return the silver layer directory."""
        return self.lakehouse_dir / "silver_chunks"

    @property
    def gold_dir(self) -> Path:
        """Return the gold layer directory."""
        return self.lakehouse_dir / "gold_embeddings"

    @property
    def chroma_dir(self) -> Path:
        """Return the Chroma persistence directory."""
        return self.project_root / "vector_store" / "chroma"

    @property
    def logs_dir(self) -> Path:
        """Return the logs directory."""
        return self.project_root / "logs"

    @property
    def audit_log_path(self) -> Path:
        """Return the audit log file path."""
        return self.logs_dir / "audit_log.jsonl"

    @property
    def openmetadata_assets_path(self) -> Path:
        """Return the simulated OpenMetadata asset path."""
        return self.project_root / "metadata" / "openmetadata_assets.json"

    @property
    def local_secrets_path(self) -> Path:
        """Return the local secrets file path."""
        return self.project_root / ".local" / "secrets.json"

    # --- Scalar convenience shims ---

    @property
    def embedding_model(self) -> str:
        """Return the embedding model name."""
        return self.embedding.model

    @property
    def embedding_dim(self) -> int:
        """Return the embedding dimension."""
        return self.embedding.dim

    @property
    def chunk_size(self) -> int:
        """Return the chunk size."""
        return self.pipeline.chunk_size

    @property
    def chunk_overlap(self) -> int:
        """Return the chunk overlap."""
        return self.pipeline.chunk_overlap

    @property
    def default_top_k(self) -> int:
        """Return the default top_k."""
        return self.pipeline.default_top_k

    @property
    def retrieval_candidate_multiplier(self) -> int:
        """Return the retrieval candidate multiplier."""
        return self.pipeline.retrieval_candidate_multiplier

    @property
    def chroma_collection_name(self) -> str:
        """Return the Chroma collection name."""
        return self.storage.chroma_collection_name

    @property
    def secret_key_env_var(self) -> str:
        """Return the secret key environment variable name."""
        return self.security.secret_key_env_var
