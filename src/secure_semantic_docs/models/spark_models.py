"""Spark session and Iceberg catalog configuration dataclasses."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SparkConfig:
    """PySpark session settings.

    ``managed`` and ``log_level`` are framework-level controls.
    All other entries in the YAML ``spark`` section are raw Spark
    configuration key-value pairs stored in ``confs`` and passed
    directly to :class:`pyspark.SparkConf`.
    """

    managed: bool = False
    log_level: str = "WARN"
    confs: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class IcebergConfig:
    """Apache Iceberg catalog and runtime settings.

    Disabled by default for local development (Parquet is used instead).
    Enabled in Docker / production via ``config.prod.yml`` when
    ``DOCSEC_ENV=prod``.

    Table layout::

        <catalog>.bronze.documents   -- bronze layer

    The namespace is created with ``CREATE NAMESPACE IF NOT EXISTS`` before
    the first write.

    ``catalog_type="rest"`` uses the Iceberg REST catalog (Docker default).
    ``catalog_type="hadoop"`` uses a file-system catalog (no extra service).
    """

    enabled: bool = False
    catalog_name: str = "local"
    catalog_type: str = "rest"
    catalog_uri: str = "http://iceberg-rest:8181"
    warehouse: str = "/app/lakehouse/iceberg_warehouse"
