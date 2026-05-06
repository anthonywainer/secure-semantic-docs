"""Immutable root configuration dataclass for docsec."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from secure_semantic_docs.core.settings import BaseSettings
from secure_semantic_docs.models.reader_models import ReadersConfig
from secure_semantic_docs.models.spark_models import IcebergConfig, SparkConfig
from secure_semantic_docs.models.writer_models import WritersConfig


def _project_root() -> Path:
    """Resolve the project root directory.

    Resolution order:
    1. ``DOCSEC_PROJECT_ROOT`` environment variable.
    2. ``SSD_PROJECT_ROOT`` environment variable (legacy alias).
    3. Auto-detected as four levels above this file.
    """
    env_root = (
            os.environ.get(BaseSettings.DOCSEC_PROJECT_ROOT)
            or os.environ.get(BaseSettings.DOCSEC_PROJECT_ROOT_LEGACY)
    )
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class Config:
    """Immutable project-wide configuration assembled from YAML files."""

    project_root: Path = field(default_factory=_project_root)
    spark: SparkConfig = field(default_factory=SparkConfig)
    iceberg: IcebergConfig = field(default_factory=IcebergConfig)
    readers: ReadersConfig = field(default_factory=ReadersConfig)
    writers: WritersConfig = field(default_factory=WritersConfig)

    @property
    def data_dir(self) -> Path:
        """Return the synthetic_data directory."""
        return self.project_root / "synthetic_data"

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
    def logs_dir(self) -> Path:
        """Return the logs directory."""
        return self.project_root / "logs"
