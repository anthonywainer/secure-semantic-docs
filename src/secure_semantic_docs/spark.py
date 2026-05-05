"""Spark session factory with optional Apache Iceberg catalog support.

Usage::

    from secure_semantic_docs.spark import build_spark_session

    spark = build_spark_session()          # Parquet mode (local)
    spark = build_spark_session(config)    # Iceberg mode when cfg.iceberg.enabled

When ``config.iceberg.enabled`` is ``True`` the session is configured with:

- ``org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions``
- A named Spark catalog (``spark.sql.catalog.<catalog_name>``) backed by either
  a REST catalog (default, Docker) or a Hadoop catalog (file-system only).
- The Iceberg Spark runtime JAR pulled from Maven via ``spark.jars.packages``.

Iceberg JAR compatibility note
-------------------------------
PySpark 3.5 uses Scala 2.12 -> ``iceberg-spark-runtime-3.5_2.12:1.6.1``
PySpark 4.0+ uses Scala 2.13 -> ``iceberg-spark-runtime-4.0_2.13:<version>``
Update ``iceberg.spark_packages`` in ``config.prod.yml`` once Iceberg 1.7.0
(Spark 4.x support) is released.
"""

import logging

from pyspark.sql import SparkSession

from secure_semantic_docs.config import Config, IcebergConfig, load_config

logger = logging.getLogger(__name__)


def build_spark_session(config: Config | None = None) -> SparkSession:
    """Build and return a :class:`SparkSession` driven by :class:`~secure_semantic_docs.config.SparkConfig`.

    Iceberg catalog extensions and JAR packages are added automatically when
    ``config.iceberg.enabled`` is ``True``.
    """
    cfg = config or load_config()
    sp = cfg.spark

    builder = (
        SparkSession.builder.master(sp.master)
        .appName(sp.app_name)
        .config("spark.sql.shuffle.partitions", str(sp.shuffle_partitions))
        .config("spark.driver.memory", sp.driver_memory)
        .config("spark.executor.memory", sp.executor_memory)
    )

    if cfg.iceberg.enabled:
        builder = _configure_iceberg(builder, cfg.iceberg)
        logger.info(
            "Iceberg enabled -- catalog=%s type=%s warehouse=%s",
            cfg.iceberg.catalog_name,
            cfg.iceberg.catalog_type,
            cfg.iceberg.warehouse
        )
    else:
        logger.debug("Iceberg disabled -- using Parquet lakehouse")

    session = builder.getOrCreate()
    session.sparkContext.setLogLevel(sp.log_level)
    return session


def _configure_iceberg(
    builder: SparkSession.Builder, ic: IcebergConfig
) -> SparkSession.Builder:
    """Add Iceberg extensions and catalog configuration to *builder*.

    JAR resolution order:
    1. ``ic.spark_jars`` -- pre-downloaded local path (Docker production).
    2. ``ic.spark_packages`` -- Maven coordinates (dev / CI with internet).
    """
    cat = ic.catalog_name
    if ic.spark_jars:
        builder = builder.config("spark.jars", ic.spark_jars)
    elif ic.spark_packages:
        builder = builder.config("spark.jars.packages", ic.spark_packages)
    builder = (
        builder.config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions"
        )
        .config(f"spark.sql.catalog.{cat}", "org.apache.iceberg.spark.SparkCatalog")
        .config(f"spark.sql.catalog.{cat}.type", ic.catalog_type)
        .config(f"spark.sql.catalog.{cat}.warehouse", ic.warehouse)
    )
    if ic.catalog_type == "rest":
        builder = builder.config(f"spark.sql.catalog.{cat}.uri", ic.catalog_uri)
    return builder
