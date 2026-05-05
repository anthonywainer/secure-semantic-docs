"""Configuration package for docsec.

Usage::

    from secure_semantic_docs.config import load_config, Config, SparkConfig, ReadersConfig, WritersConfig

    cfg = load_config()
    print(cfg.spark.master, cfg.writers.parquet.compression)
"""

from secure_semantic_docs.config._loader import deep_merge, load_config, load_yaml_file
from secure_semantic_docs.config._schema import (
    Config,
    CsvReaderConfig,
    CsvWriterConfig,
    EmbeddingConfig,
    IcebergConfig,
    JsonReaderConfig,
    JsonWriterConfig,
    ParquetReaderConfig,
    ParquetWriterConfig,
    PipelineConfig,
    ReadersConfig,
    SecurityConfig,
    SparkConfig,
    StorageConfig,
    WritersConfig,
)

__all__ = [
    "load_config",
    "load_yaml_file",
    "deep_merge",
    "Config",
    "EmbeddingConfig",
    "PipelineConfig",
    "StorageConfig",
    "SecurityConfig",
    "SparkConfig",
    "IcebergConfig",
    "ParquetReaderConfig",
    "JsonReaderConfig",
    "CsvReaderConfig",
    "ReadersConfig",
    "ParquetWriterConfig",
    "JsonWriterConfig",
    "CsvWriterConfig",
    "WritersConfig",
]
