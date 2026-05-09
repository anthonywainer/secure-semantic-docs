"""Gold layer: embedding generation using SentenceTransformers.

Embeddings are generated partition-by-partition via PySpark ``mapPartitions``
to avoid loading the model once per row.  All embedding logic lives in the
:mod:`secure_semantic_docs.embeddings` package.

Schema is defined in::

    resources/catalog_metadata/gold_embeddings.ddl

and loaded lazily via :func:`~secure_semantic_docs.storage.schemas.load_schema`.
"""

import logging

from pyspark.sql import SparkSession

from secure_semantic_docs.core import ingest_log_execution, configure_logging, BaseSettings
from secure_semantic_docs.core.spark import build_spark_session
from secure_semantic_docs.embeddings import generate_embeddings
from secure_semantic_docs.io import SparkReader, SparkWriter
from secure_semantic_docs.loader import load_config
from secure_semantic_docs.models import Config


@ingest_log_execution
def main() -> None:
    """Entry point: configure logging, build Spark, then run :func:`ingest`."""
    logging.getLogger("py4j").setLevel(logging.ERROR)
    configure_logging()
    pipeline_config = load_config()
    spark_session = build_spark_session(pipeline_config)
    ingest(spark_session, pipeline_config)


def ingest(spark_session: SparkSession, pipeline_config: Config | None = None) -> None:
    """Run the gold ingestion pipeline.

    Parameters
    ----------
    spark_session:
        Active SparkSession to use.
    pipeline_config:
        Configuration instance. When *None*, loaded via :func:`load_config`.
    """
    logger = logging.getLogger(BaseSettings.APP_NAME)
    effective_config = pipeline_config or load_config()

    logger.info("STEP 1 -- Load silver chunks")
    silver_chunks_options = effective_config.readers["silver_chunks"]
    silver_chunks_df = SparkReader(spark_session).read(**silver_chunks_options.options)

    logger.info("STEP 2 -- Generate embeddings")
    gold_embeddings_df = generate_embeddings(spark_session, silver_chunks_df, effective_config)

    logger.info("STEP 3 -- Write gold layer")
    gold_embeddings_options = effective_config.writers["gold_embeddings"]
    SparkWriter(spark_session).write(
        gold_embeddings_df, **gold_embeddings_options.options
    )
    logger.info("Gold write complete")


if __name__ == "__main__":  # pragma: no cover
    main()
