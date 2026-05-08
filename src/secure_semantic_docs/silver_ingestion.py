"""Silver layer: text chunking with full provenance metadata.

Each chunk carries a copy of the document metadata so downstream layers
have complete provenance without joining back to bronze.

Schema is defined in::

    resources/catalog_metadata/silver_chunks.ddl

and loaded lazily via :func:`~secure_semantic_docs.storage.schemas.load_schema`.
"""
import logging
from collections.abc import Iterable

from pyspark.sql import DataFrame, Row, SparkSession

from secure_semantic_docs.core import ingest_log_execution, configure_logging, BaseSettings
from secure_semantic_docs.core.sensitive import enrich_chunks_with_sensitivity
from secure_semantic_docs.core.spark import build_spark_session
from secure_semantic_docs.io import SparkWriter, SparkReader
from secure_semantic_docs.loader import load_config
from secure_semantic_docs.models import Config
from secure_semantic_docs.processing import SensitiveSilverChunkRow, chunk_document
from secure_semantic_docs.storage.schemas import load_schema


@ingest_log_execution
def main() -> None:
    """Entry point: configure logging, build Spark, then run :func:`ingest`."""
    logging.getLogger("py4j").setLevel(logging.ERROR)
    configure_logging()
    pipeline_config = load_config()
    spark_session = build_spark_session(pipeline_config)
    ingest(spark_session, pipeline_config)


def ingest(spark_session: SparkSession, pipeline_config: Config | None = None) -> None:
    """Run the silver ingestion pipeline.

    Parameters
    ----------
    spark_session:
        Active SparkSession to use.
    pipeline_config:
        Configuration instance. When *None*, loaded via :func:`load_config`.
    """
    logger = logging.getLogger(BaseSettings.APP_NAME)
    effective_config = pipeline_config or load_config()

    logger.info("STEP 1 -- Load bronze documents")
    bronze_documents_options = effective_config.readers["bronze_documents"]
    bronze_documents_df = SparkReader(spark_session).read(**bronze_documents_options.options)

    logger.info("STEP 2 -- Chunking")
    silver_chunks_df = process_bronze_to_silver(
        spark_session, bronze_documents_df, effective_config
    )

    logger.info("STEP 3 -- Write chunks")
    silver_chunks_options = effective_config.writers["silver_chunks"]
    SparkWriter(spark_session).write(
        silver_chunks_df, **silver_chunks_options.options
    )
    logger.info("Silver write complete")


def process_bronze_to_silver(
        spark_session: SparkSession,
        bronze_documents_df: DataFrame,
        config: Config | None = None
) -> DataFrame:
    """Transform the bronze DataFrame into the silver chunks DataFrame."""
    effective_config = config or Config()
    chunk_size = effective_config.chunking.chunk_size
    chunk_overlap = effective_config.chunking.chunk_overlap

    def _build_sensitive_chunk_rows(
            bronze_document_rows: Iterable[Row]
    ) -> Iterable[SensitiveSilverChunkRow]:
        for bronze_document_row in bronze_document_rows:
            bronze_document_payload = dict(bronze_document_row.asDict())
            raw_chunks = chunk_document(bronze_document_payload, chunk_size, chunk_overlap)
            for enriched in enrich_chunks_with_sensitivity(raw_chunks):
                yield (
                    str(enriched["chunk_id"]),
                    str(enriched["document_id"]),
                    int(enriched["chunk_index"]),  # type: ignore[arg-type]
                    str(enriched["chunk_text"]),
                    str(enriched["classification"]),
                    list(enriched["allowed_roles"]),  # type: ignore[arg-type]
                    str(enriched["owner"]),
                    str(enriched["department"]),
                    str(enriched["version"]),
                    str(enriched["source_path"]),
                    str(enriched["document_hash"]),
                    float(enriched["sensitivity_score"]),  # type: ignore[arg-type]
                    list(enriched["detected_sensitive_types"]),  # type: ignore[arg-type]
                    bool(enriched["requires_encryption"]),
                    bool(enriched["requires_restricted_access"])
                )

    silver_chunks_rdd = bronze_documents_df.rdd.mapPartitions(_build_sensitive_chunk_rows)
    return spark_session.createDataFrame(
        silver_chunks_rdd, schema=load_schema("silver_chunks")
    )


if __name__ == "__main__":  # pragma: no cover
    main()
