import logging
from datetime import datetime, UTC

from pyspark.sql import SparkSession
from pyspark.sql.functions import input_file_name, col, coalesce, lit, element_at, split

from secure_semantic_docs.core import BaseSettings, configure_logging, ingest_log_execution
from secure_semantic_docs.core.spark import build_spark_session
from secure_semantic_docs.io import SparkReader, SparkWriter
from secure_semantic_docs.loader import Config, load_config
from secure_semantic_docs.storage import load_schema


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
    metadata_options = config.readers["metadata_documents"]
    metadata_df = SparkReader(spark).read(**metadata_options.options).select(
        col("document_id"),
        col("title"),
        col("source_path"),
        col("classification"),
        col("owner"),
        col("department"),
        col("allowed_roles"),
        col("version"),
        col("created_at"),
        col("contains_sensitive_info"),
        col("document_hash"),
        element_at(split(col("source_path"), "/"), -1).alias("_filename")
    )

    logger.info("STEP 2 -- Load documents")
    document_reader_options = config.readers["raw_documents"]
    raw_texts_df = SparkReader(spark).read(**document_reader_options.options).select(
        element_at(split(input_file_name(), "/"), -1).alias("_filename"),
        col("value").alias("raw_text")
    )

    logger.info("STEP 3 -- Join document with metadata")
    ingestion_ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    document_schema = load_schema("bronze_documents")

    document_with_metadata_df = metadata_df.join(
        raw_texts_df, "_filename", "left"
    ).select(*[_cast_field(f, ingestion_ts) for f in document_schema])

    logger.info("STEP 4 -- Bronze write")
    document_writer_options = config.writers["bronze_documents"]
    SparkWriter(spark).write(
        document_with_metadata_df, **document_writer_options.options
    )
    logger.info("Bronze write complete")


def _cast_field(f, ingestion_ts: str):
    if f.name == "raw_text":
        return coalesce(col("raw_text"), lit("")).cast(f.dataType).alias("raw_text")
    if f.name == "ingestion_timestamp":
        return lit(ingestion_ts).cast(f.dataType).alias("ingestion_timestamp")
    return col(f.name).cast(f.dataType)


if __name__ == "__main__":  # pragma: no cover
    main()
