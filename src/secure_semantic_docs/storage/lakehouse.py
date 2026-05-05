"""Lakehouse read/write helpers for bronze, silver, and gold layers.

Local mode (default, ``iceberg.enabled = False``):
    All three layers are stored as Parquet files under ``lakehouse/``.

Production mode (Docker, ``iceberg.enabled = True``):
    Layers are written to Apache Iceberg tables.  Each layer has its own
    Iceberg namespace (schema) so the catalog layout is::

        <catalog_name>.bronze.documents   -- bronze layer
        <catalog_name>.silver.chunks      -- silver layer
        <catalog_name>.gold.embeddings    -- gold layer

    Namespaces are created automatically with
    ``CREATE NAMESPACE IF NOT EXISTS`` before the first write.

Iceberg writes use ``DataFrame.writeTo(<table>).using("iceberg").createOrReplace()``.
For incremental upserts replace ``createOrReplace`` with a Spark SQL ``MERGE INTO``
statement once the pipeline supports partitioned ingestion.

Iceberg reads use ``SparkSession.table(<table>)``.

Iceberg JAR compatibility note
-------------------------------
PySpark 3.5 uses Scala 2.12  -> ``iceberg-spark-runtime-3.5_2.12``
PySpark 4.0+ uses Scala 2.13 -> ``iceberg-spark-runtime-4.0_2.13``
Set the correct package in ``iceberg.spark_packages`` in ``config.prod.yml``.
"""

import logging
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import StructType

from secure_semantic_docs.config import Config, IcebergConfig, load_config
from secure_semantic_docs.exceptions import IngestionError
from secure_semantic_docs.storage.schemas import load_schema

logger = logging.getLogger(__name__)

# Maps the logical table key used throughout the codebase to
# (iceberg_namespace, iceberg_table_name).
# Full identifier: <catalog_name>.<namespace>.<table>
_TABLE_MAP: dict[str, tuple[str, str]] = {
    "bronze_documents": ("bronze", "documents"),
    "silver_chunks": ("silver", "chunks"),
    "gold_embeddings": ("gold", "embeddings")
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _iceberg_table_id(ic: IcebergConfig, logical_name: str) -> str:
    """Return the fully qualified Iceberg table identifier.

    ``bronze_documents`` -> ``<catalog>.bronze.documents``
    ``silver_chunks``    -> ``<catalog>.silver.chunks``
    ``gold_embeddings``  -> ``<catalog>.gold.embeddings``
    """
    if logical_name not in _TABLE_MAP:
        raise ValueError(
            f"Unknown logical table name '{logical_name}'. "
            f"Valid names: {list(_TABLE_MAP)}"
        )
    namespace, table = _TABLE_MAP[logical_name]
    return f"{ic.catalog_name}.{namespace}.{table}"


def _ensure_namespace(
    spark: SparkSession, ic: IcebergConfig, logical_name: str
) -> None:
    """Create the Iceberg namespace for *logical_name* if it does not exist."""
    namespace, _ = _TABLE_MAP[logical_name]
    ns_id = f"{ic.catalog_name}.{namespace}"
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {ns_id}")
    logger.debug("Namespace ready: %s", ns_id)


def _write_parquet(df: DataFrame, path: Path, config: Config) -> None:
    pw = config.writers.parquet
    path.mkdir(parents=True, exist_ok=True)
    df.write.mode(pw.mode).option("compression", pw.compression).parquet(str(path))
    logger.info("Parquet write -> %s (mode=%s)", path, pw.mode)


def _write_iceberg(
    df: DataFrame, logical_name: str, spark: SparkSession, config: Config
) -> None:
    ic = config.iceberg
    _ensure_namespace(spark, ic, logical_name)
    table_id = _iceberg_table_id(ic, logical_name)
    (df.writeTo(table_id).using("iceberg").createOrReplace())
    logger.info("Iceberg write -> %s", table_id)


def _read_parquet(
    spark: SparkSession,
    path: Path,
    schema: StructType | None,
    layer_name: str,
    config: Config
) -> DataFrame:
    if not path.exists():
        raise IngestionError(
            f"{layer_name} directory not found: {path}. "
            "Run the corresponding pipeline step first."
        )
    pr = config.readers.parquet
    reader = spark.read.option("mergeSchema", str(pr.merge_schema).lower())
    if schema is not None:
        reader = reader.schema(schema)
    return reader.parquet(str(path))


def _read_iceberg(spark: SparkSession, logical_name: str, config: Config) -> DataFrame:
    ic = config.iceberg
    table_id = _iceberg_table_id(ic, logical_name)
    logger.debug("Iceberg read <- %s", table_id)
    return spark.table(table_id)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_layer(
    df: DataFrame,
    table_name: str,
    path: Path,
    config: Config | None = None,
    spark: SparkSession | None = None
) -> None:
    """Write *df* to the appropriate lakehouse format.

    Routes to Iceberg when ``config.iceberg.enabled`` is ``True``,
    otherwise writes Parquet to *path*.

    Parameters
    ----------
    df:
        The DataFrame to persist.
    table_name:
        Logical table name (``"bronze_documents"``, ``"silver_chunks"``,
        or ``"gold_embeddings"``).  Iceberg table identifier is derived
        from this: ``bronze_documents`` -> ``<catalog>.bronze.documents``.
    path:
        Filesystem path for the Parquet fallback.
    config:
        Optional explicit :class:`~secure_semantic_docs.config.Config`.
    spark:
        Active :class:`~pyspark.sql.SparkSession` -- required in Iceberg
        mode for namespace creation.  Ignored in Parquet mode.
        Falls back to ``df.sparkSession`` when not provided.
    """
    cfg = config or load_config()
    if cfg.iceberg.enabled:
        active_spark = spark if spark is not None else df.sparkSession
        _write_iceberg(df, table_name, active_spark, cfg)
    else:
        _write_parquet(df, path, cfg)


def read_layer(
    spark: SparkSession,
    table_name: str,
    path: Path,
    schema: StructType | None = None,
    layer_name: str = "layer",
    config: Config | None = None
) -> DataFrame:
    """Read a lakehouse layer from the appropriate backend.

    Routes to Iceberg when ``config.iceberg.enabled`` is ``True``,
    otherwise reads Parquet from *path*.

    Parameters
    ----------
    spark:
        Active :class:`~pyspark.sql.SparkSession`.
    table_name:
        Logical table name used for Iceberg reads.
    path:
        Filesystem path for the Parquet fallback.
    schema:
        Optional explicit schema applied only in Parquet mode.
    layer_name:
        Human-readable name used in error messages.
    config:
        Optional explicit :class:`~secure_semantic_docs.config.Config`.
    """
    cfg = config or load_config()
    if cfg.iceberg.enabled:
        return _read_iceberg(spark, table_name, cfg)
    return _read_parquet(spark, path, schema, layer_name, cfg)


def read_bronze(spark: SparkSession, config: Config | None = None) -> DataFrame:
    """Read the bronze documents layer."""
    cfg = config or load_config()
    return read_layer(
        spark,
        "bronze_documents",
        cfg.bronze_dir,
        load_schema("bronze_documents"),
        "Bronze",
        cfg
    )


def read_silver(spark: SparkSession, config: Config | None = None) -> DataFrame:
    """Read the silver chunks layer."""
    cfg = config or load_config()
    return read_layer(
        spark,
        "silver_chunks",
        cfg.silver_dir,
        load_schema("silver_chunks"),
        "Silver",
        cfg
    )


def read_gold(spark: SparkSession, config: Config | None = None) -> DataFrame:
    """Read the gold embeddings layer."""
    cfg = config or load_config()
    return read_layer(
        spark,
        "gold_embeddings",
        cfg.gold_dir,
        load_schema("gold_embeddings"),
        "Gold",
        cfg
    )
