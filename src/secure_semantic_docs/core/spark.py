"""Spark session factory with optional Apache Iceberg catalog support.

Usage::

    from secure_semantic_docs.core.spark import build_spark_session

    spark = build_spark_session()          # Parquet mode (local)
    spark = build_spark_session(config)    # Iceberg mode when cfg.iceberg.enabled

The session is driven entirely by the YAML config (``spark`` and ``iceberg``
sections).  All settings are passed via :class:`pyspark.SparkConf` so the
full Spark configuration surface is covered without hard-coded key names.

If an active session already exists (e.g. on Databricks) it is reused as-is.

Set ``spark.managed: true`` in the YAML to skip local Spark configuration
(all settings come from the managed cluster instead).

The ``spark`` YAML section stores raw Spark configuration keys in dotted
notation alongside two framework controls (``managed``, ``log_level``).
Any key not starting with ``managed`` or ``log_level`` is passed directly
to :class:`pyspark.SparkConf`.

Iceberg JAR compatibility note
-------------------------------
PySpark 3.5 uses Scala 2.12 -> ``iceberg-spark-runtime-3.5_2.12:1.6.1``
PySpark 4.0+ uses Scala 2.13 -> ``iceberg-spark-runtime-4.0_2.13:<version>``
Update ``spark.jars.packages`` in ``config.prod.yml`` accordingly.
"""

from __future__ import annotations

from collections.abc import Iterable

from pyspark import SparkConf
from pyspark.sql import SparkSession

from secure_semantic_docs.core.logging import get_logger
from secure_semantic_docs.core.settings import BaseSettings
from secure_semantic_docs.loader import Config, IcebergConfig, load_config

logger = get_logger(BaseSettings.APP_NAME)


def build_spark_session(config: Config | None = None) -> SparkSession:
    """Return an active :class:`SparkSession` driven by the YAML config.

    If a session is already active (e.g. on Databricks) it is returned as-is.
    Otherwise a new session is created using :class:`pyspark.SparkConf` built
    from the ``spark`` (and optionally ``iceberg``) sections of the YAML config.

    When ``spark.managed`` is ``true`` in the YAML, local Spark configuration
    is skipped and cluster defaults are used.
    """
    active = SparkSession.getActiveSession()
    if active is not None:
        logger.debug("Reusing active SparkSession -- app=%s", active.sparkContext.appName)
        return active

    cfg = config or load_config()

    if cfg.spark.managed:
        logger.debug("Managed Spark environment -- skipping local configuration")
        confs: list[tuple[str, str]] = []
    else:
        confs = list(cfg.spark.confs.items())

    if cfg.iceberg.enabled:
        confs += _iceberg_confs(cfg.iceberg)
        logger.info(
            "Iceberg enabled -- catalog=%s type=%s warehouse=%s",
            cfg.iceberg.catalog_name,
            cfg.iceberg.catalog_type,
            cfg.iceberg.warehouse
        )
    else:
        logger.debug("Iceberg disabled -- using Parquet lakehouse")

    spark_conf = SparkConf().setAll(_merge_configurations(confs))
    session = SparkSession.builder.config(conf=spark_conf).getOrCreate()
    session.sparkContext.setLogLevel(cfg.spark.log_level)
    logger.info(
        "SparkSession started -- app=%s master=%s",
        cfg.spark.confs.get("spark.app.name"),
        cfg.spark.confs.get("spark.master")
    )
    return session


def _iceberg_confs(ic: IcebergConfig) -> list[tuple[str, str]]:
    """Return Iceberg catalog ``(key, value)`` tuples from *ic*."""
    cat = ic.catalog_name
    confs: list[tuple[str, str]] = [
        (
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions"
        ),
        (f"spark.sql.catalog.{cat}", "org.apache.iceberg.spark.SparkCatalog"),
        (f"spark.sql.catalog.{cat}.type", ic.catalog_type),
        (f"spark.sql.catalog.{cat}.warehouse", ic.warehouse)
    ]
    if ic.catalog_type == "rest":
        confs.append((f"spark.sql.catalog.{cat}.uri", ic.catalog_uri))
    return confs


def _merge_configurations(
        configurations: Iterable[tuple[str, str]]
) -> list[tuple[str, str]]:
    """Merge duplicate keys by concatenating values with commas.

    Useful for keys like ``spark.jars.packages`` and
    ``spark.sql.extensions`` that accept comma-separated lists.
    """
    merged: dict[str, str] = {}
    for key, value in configurations:
        merged[key] = f"{merged[key]},{value}" if key in merged else value
    return list(merged.items())
