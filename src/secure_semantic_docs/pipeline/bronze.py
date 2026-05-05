"""Bronze layer ingestion using PySpark.

Reads raw documents and metadata to produce the bronze_documents dataset.
The write/read path is routed through
:func:`~secure_semantic_docs.storage.lakehouse.write_layer` and
:func:`~secure_semantic_docs.storage.lakehouse.read_layer` so switching
between Parquet (local) and Apache Iceberg (Docker/production) requires
no changes in this module.

Schema is defined in::

    resources/schemas/bronze_documents.ddl

and loaded lazily via :func:`~secure_semantic_docs.storage.schemas.load_schema`.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession

from secure_semantic_docs.config import Config, load_config
from secure_semantic_docs.exceptions import IngestionError
from secure_semantic_docs.spark import build_spark_session
from secure_semantic_docs.storage.lakehouse import read_layer, write_layer
from secure_semantic_docs.storage.schemas import load_schema

logger = logging.getLogger(__name__)

# Backward-compatible alias -- prefer build_spark_session going forward.
create_spark_session = build_spark_session


def _load_metadata(config: Config) -> dict[str, dict[str, object]]:
    """Load document metadata keyed by document id."""
    metadata_path = config.metadata_dir / "documents_metadata.json"
    if not metadata_path.exists():
        raise IngestionError(
            f"Metadata file not found: {metadata_path}. "
            "Run data_generator.save_dataset() first."
        )
    records: list[dict[str, object]] = json.loads(
        metadata_path.read_text(encoding="utf-8")
    )
    return {str(record["document_id"]): record for record in records}


def _read_raw_text(source_path: str, project_root: Path) -> str:
    """Read raw text from a document file relative to project root."""
    full_path = project_root / source_path
    if not full_path.exists():
        logger.warning("Document not found: %s", full_path)
        return ""
    return full_path.read_text(encoding="utf-8")


def ingest_documents(spark: SparkSession, config: Config | None = None) -> None:
    """Ingest raw documents into the bronze Parquet layer."""
    cfg = config or load_config()
    metadata_by_id = _load_metadata(cfg)
    ingestion_ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: list[dict[str, object]] = []

    for doc_id, meta in metadata_by_id.items():
        rows.append(
            {
                "document_id": doc_id,
                "title": meta["title"],
                "source_path": meta["source_path"],
                "raw_text": _read_raw_text(str(meta["source_path"]), cfg.project_root),
                "classification": meta["classification"],
                "owner": meta["owner"],
                "department": meta["department"],
                "allowed_roles": meta["allowed_roles"],
                "version": meta["version"],
                "created_at": meta["created_at"],
                "contains_sensitive_info": meta["contains_sensitive_info"],
                "document_hash": meta["document_hash"],
                "ingestion_timestamp": ingestion_ts
            }
        )

    if not rows:
        raise IngestionError("No documents found to ingest.")

    schema = load_schema("bronze_documents")
    bronze_df = spark.createDataFrame(rows, schema=schema)
    write_layer(bronze_df, "bronze_documents", cfg.bronze_dir, cfg)
    logger.info("Ingested %d documents into bronze", len(rows))


def read_bronze(spark: SparkSession, config: Config | None = None) -> DataFrame:
    """Read the bronze dataset (Parquet or Iceberg depending on config)."""
    cfg = config or load_config()

    return read_layer(
        spark,
        "bronze_documents",
        cfg.bronze_dir,
        load_schema("bronze_documents"),
        "Bronze",
        cfg
    )
