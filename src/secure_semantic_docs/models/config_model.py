"""Immutable root configuration dataclass for docsec."""

from dataclasses import dataclass, field
from pathlib import Path

from secure_semantic_docs.core.settings import BaseSettings
from secure_semantic_docs.models.chunking_model import ChunkingConfig
from secure_semantic_docs.models.reader_models import ReadersConfig
from secure_semantic_docs.models.spark_models import IcebergConfig, SparkConfig
from secure_semantic_docs.models.writer_models import WritersConfig


@dataclass(frozen=True)
class Config:
    """Immutable project-wide configuration assembled from YAML files."""

    project_root: Path = field(default_factory=lambda: BaseSettings.project_root)
    spark: SparkConfig = field(default_factory=SparkConfig)
    iceberg: IcebergConfig = field(default_factory=IcebergConfig)
    readers: ReadersConfig = field(default_factory=ReadersConfig)
    writers: WritersConfig = field(default_factory=WritersConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)

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
