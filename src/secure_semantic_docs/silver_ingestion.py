"""Silver ingestion entry point.

Reads raw documents, builds enriched chunks via
:func:`~secure_semantic_docs.processing.chunk_builder.create_enriched_chunks`,
and writes the result.

Schema is defined in::

    resources/catalog_metadata/silver_chunks.ddl
"""
import logging

from pyspark.sql import SparkSession

from secure_semantic_docs.core import ingest_log_execution, configure_logging, BaseSettings
from secure_semantic_docs.core.spark import build_spark_session
from secure_semantic_docs.io import SparkWriter, SparkReader
from secure_semantic_docs.loader import load_config
from secure_semantic_docs.models import Config
from secure_semantic_docs.processing.chunk_builder import create_enriched_chunks


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

    logger.info("STEP 1 -- Load documents")
    documents_options = effective_config.readers["bronze_documents"]
    documents_df = SparkReader(spark_session).read(**documents_options.options)

    logger.info("STEP 2 -- Build chunks")
    chunks_df = create_enriched_chunks(spark_session, documents_df, effective_config)

    logger.info("STEP 3 -- Write chunks")
    writer_options = effective_config.writers["silver_chunks"]
    SparkWriter(spark_session).write(chunks_df, **writer_options.options)
    logger.info("Silver write complete")


if __name__ == "__main__":  # pragma: no cover
    main()
