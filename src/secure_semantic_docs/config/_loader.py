"""YAML configuration loader.

Loading order (each layer deep-merges into the previous):
  1. resources/config.yml      -- bundled base
  2. resources/config.dev.yml  -- bundled dev overrides (always applied)
  3. resources/config.prod.yml -- prod overrides (only when DOCSEC_ENV=prod)
  4. <project_root>/config.local.yml -- machine-local, git-ignored

All configuration values live in the YAML files.  The loader contains no
Python-side fallback defaults -- a missing key raises KeyError immediately.
"""

import os
from pathlib import Path
from typing import Any

import yaml

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

_RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"
_BUNDLED_BASE = [_RESOURCES_DIR / "config.yml", _RESOURCES_DIR / "config.dev.yml"]
_BUNDLED_PROD = _RESOURCES_DIR / "config.prod.yml"


def load_yaml_file(path: Path) -> dict[str, Any]:
    """Load a YAML file; return an empty dict when the file does not exist."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        result = yaml.safe_load(fh) or {}
    return result if isinstance(result, dict) else {}


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, returning a new dict."""
    result: dict[str, Any] = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(project_root: Path | None = None) -> Config:
    """Build and return a :class:`Config` from YAML files.

    Parameters
    ----------
    project_root:
        Optional explicit project root.  When *None*, taken from the
        ``DOCSEC_PROJECT_ROOT`` env var, then ``SSD_PROJECT_ROOT`` (legacy),
        then auto-detected as four directories above this file.
    """
    if project_root is None:
        env_root = os.environ.get("DOCSEC_PROJECT_ROOT") or os.environ.get(
            "SSD_PROJECT_ROOT"
        )
        project_root = (
            Path(env_root)
            if env_root
            else Path(__file__).resolve().parent.parent.parent.parent
        )

    raw: dict[str, Any] = {}
    for bundled in _BUNDLED_BASE:
        raw = deep_merge(raw, load_yaml_file(bundled))

    if os.environ.get("DOCSEC_ENV") == "prod":
        raw = deep_merge(raw, load_yaml_file(_BUNDLED_PROD))

    raw = deep_merge(raw, load_yaml_file(project_root / "config.local.yml"))

    rdr = raw["readers"]
    wtr = raw["writers"]

    return Config(
        project_root=project_root,
        embedding=EmbeddingConfig(**raw["embedding"]),
        pipeline=PipelineConfig(**raw["pipeline"]),
        storage=StorageConfig(**raw["storage"]),
        security=SecurityConfig(**raw["security"]),
        spark=SparkConfig(**raw["spark"]),
        iceberg=IcebergConfig(**raw["iceberg"]),
        readers=ReadersConfig(
            parquet=ParquetReaderConfig(**rdr["parquet"]),
            json=JsonReaderConfig(**rdr["json"]),
            csv=CsvReaderConfig(**rdr["csv"]),
        ),
        writers=WritersConfig(
            parquet=ParquetWriterConfig(**wtr["parquet"]),
            json=JsonWriterConfig(**wtr["json"]),
            csv=CsvWriterConfig(**wtr["csv"]),
        ),
    )
