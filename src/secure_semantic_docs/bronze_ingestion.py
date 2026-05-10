"""Bronze ingestion entry point."""
import logging

from pyspark.sql import SparkSession

from secure_semantic_docs.core import BaseSettings, configure_logging, ingest_log_execution
from secure_semantic_docs.core.spark import build_spark_session
from secure_semantic_docs.processing.metadata_builder import conform_document_metadata
from secure_semantic_docs.io import SparkReader, SparkWriter
from secure_semantic_docs.loader import Config, load_config


@ingest_log_execution
def main() -> None:
    """Entry point: configure logging, build Spark, then run :func:`ingest`."""
    logging.getLogger("py4j").setLevel(logging.ERROR)
    configure_logging()
    config = load_config()
    spark = build_spark_session(config)
    ingest(spark, config)


def ingest(spark: SparkSession, cfg: Config | None = None) -> None:
    """Run the bronze ingestion pipeline.

    Parameters
    ----------
    spark:
        Active SparkSession to use.
    cfg:
        Configuration instance. When *None*, loaded via :func:`load_config`.
    """
    logger = logging.getLogger(BaseSettings.APP_NAME)
    config = cfg or load_config()

    logger.info("STEP 1 -- Load metadata")
    reader_options = config.readers["metadata_documents"]
    raw_df = SparkReader(spark).read(**reader_options.options)

    logger.info("STEP 2 -- Processing")
    documents_df = conform_document_metadata(raw_df)

    logger.info("STEP 3 -- Write bronze")
    writer_options = config.writers["bronze_documents"]
    SparkWriter(spark).write(documents_df, **writer_options.options)


if __name__ == "__main__":  # pragma: no cover
    main()
