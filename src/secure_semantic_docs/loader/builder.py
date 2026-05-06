"""Config builder: assembles a Config instance from YAML files.

Loading order (each layer deep-merges into the previous):
  1. resources/config.yml      -- bundled base
  2. resources/config.dev.yml  -- bundled dev overrides (always applied)
  3. resources/config.prod.yml -- prod overrides (only when DOCSEC_ENV=prod)
  4. <project_root>/config.local.yml -- machine-local, git-ignored

All configuration values live in the YAML files.  The builder contains no
Python-side fallback defaults -- a missing key raises KeyError immediately.

Reader/writer entries use the format::

    readers:
      my_source:
        stream: false
        options:
          format: csv
          path: "{env[MY_DIR]}/synthetic_data/my_source.csv"

Values of the form ``{env[VAR]}`` are expanded from environment variables at
load time.  Unknown variables expand to an empty string.
"""

import os
import re
from pathlib import Path

from secure_semantic_docs.core.logging import get_logger
from secure_semantic_docs.core.settings import BaseSettings
from secure_semantic_docs.loader.yaml_utils import deep_merge, load_yaml_file
from secure_semantic_docs.models.config_model import Config
from secure_semantic_docs.models.reader_models import ReaderEntry, ReadersConfig
from secure_semantic_docs.models.spark_models import IcebergConfig, SparkConfig
from secure_semantic_docs.models.writer_models import WriterEntry, WritersConfig

_RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"
_BUNDLED_BASE = [_RESOURCES_DIR / "config.yml", _RESOURCES_DIR / "config.dev.yml"]
_BUNDLED_PROD = _RESOURCES_DIR / "config.prod.yml"

_ENV_PATTERN = re.compile(r"\{env\[([^\]]+)\]\}")
_RESOURCES_PATTERN = re.compile(r"\{resources\}")

logger = get_logger(BaseSettings.APP_NAME)


def _expand_env(value: str, project_root: Path) -> str:
    """Expand ``{env[VAR]}`` and ``{resources}`` placeholders.

    ``{env[DOCSEC_PROJECT_ROOT]}`` resolves to *project_root* when the
    environment variable is not set, so paths are always valid.
    """

    def _resolve_var(m: re.Match) -> str:
        var = m.group(1)
        if var == BaseSettings.DOCSEC_PROJECT_ROOT:
            return os.environ.get(var) or str(project_root)
        return os.environ.get(var, "")

    value = _ENV_PATTERN.sub(_resolve_var, value)
    return _RESOURCES_PATTERN.sub(str(_RESOURCES_DIR), value)


def _expand_options(options: dict, project_root: Path) -> dict:
    """Recursively expand env placeholders in option values."""
    return {
        k: _expand_env(v, project_root) if isinstance(v, str) else v
        for k, v in options.items()
    }


def _build_spark_config(raw: dict) -> SparkConfig:
    """Extract ``SparkConfig`` from a raw YAML dict.

    ``managed`` and ``log_level`` are popped as framework-level controls.
    All remaining keys (actual Spark conf keys in dotted notation) are
    stored in ``confs``, filtering out any empty-string values.
    """
    spark_raw = dict(raw)
    managed = bool(spark_raw.pop("managed", False))
    log_level = str(spark_raw.pop("log_level", "WARN"))
    confs = {k: str(v) for k, v in spark_raw.items() if str(v)}
    return SparkConfig(managed=managed, log_level=log_level, confs=confs)


def _build_readers(raw: dict, project_root: Path) -> ReadersConfig:
    entries: dict[str, ReaderEntry] = {}
    for name, block in raw.items():
        block = block or {}
        entries[name] = ReaderEntry(
            stream=bool(block.get("stream", False)),
            options=_expand_options(dict(block.get("options") or {}), project_root)
        )
        logger.debug("Reader loaded: %s (stream=%s)", name, entries[name].stream)
    return ReadersConfig(entries=entries)


def _build_writers(raw: dict, project_root: Path) -> WritersConfig:
    entries: dict[str, WriterEntry] = {}
    for name, block in raw.items():
        block = block or {}
        entries[name] = WriterEntry(
            stream=bool(block.get("stream", False)),
            options=_expand_options(dict(block.get("options") or {}), project_root)
        )
        logger.debug("Writer loaded: %s (stream=%s)", name, entries[name].stream)
    return WritersConfig(entries=entries)


def _load_layer(raw: dict, path: Path, label: str) -> dict:
    """Merge *path* into *raw*, logging which file is applied."""
    layer = load_yaml_file(path)
    if layer:
        logger.debug("Applying config layer [%s]: %s", label, path)
        return deep_merge(raw, layer)
    logger.debug("Config layer [%s] not found or empty, skipping: %s", label, path)
    return raw


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
        env_root = (
                os.environ.get(BaseSettings.DOCSEC_PROJECT_ROOT)
                or os.environ.get(BaseSettings.DOCSEC_PROJECT_ROOT_LEGACY)
        )
        project_root = (
            Path(env_root)
            if env_root
            else Path(__file__).resolve().parent.parent.parent.parent
        )

    logger.debug("Loading config -- project_root=%s", project_root)

    raw: dict = {}
    for bundled in _BUNDLED_BASE:
        raw = _load_layer(raw, bundled, bundled.name)

    if os.environ.get("DOCSEC_ENV") == "prod":
        raw = _load_layer(raw, _BUNDLED_PROD, "prod")
    else:
        logger.debug("DOCSEC_ENV != prod, skipping %s", _BUNDLED_PROD.name)

    raw = _load_layer(raw, project_root / "config.local.yml", "local")

    cfg = Config(
        project_root=project_root,
        spark=_build_spark_config(raw.get("spark_confs") or {}),
        iceberg=IcebergConfig(**raw["iceberg"]),
        readers=_build_readers(raw.get("readers") or {}, project_root),
        writers=_build_writers(raw.get("writers") or {}, project_root)
    )

    logger.info(
        "Config loaded -- spark.master=%s iceberg.enabled=%s readers=%s writers=%s",
        cfg.spark.confs.get("spark.master"),
        cfg.iceberg.enabled,
        cfg.readers.names(),
        cfg.writers.names()
    )
    return cfg
