"""One-pass chunking and encrypted embedding generation."""

import logging
from datetime import UTC, datetime

from pyspark.sql import SparkSession

from secure_semantic_docs.core import ingest_log_execution, configure_logging, BaseSettings
from secure_semantic_docs.core.spark import build_spark_session
from secure_semantic_docs.embeddings import generate_embeddings
from secure_semantic_docs.io import SparkReader, SparkWriter
from secure_semantic_docs.loader import load_config
from secure_semantic_docs.models import Config
from secure_semantic_docs.processing.chunk_builder import (
    create_chunk_workset,
    select_persisted_chunk_columns
)
from secure_semantic_docs.processing.fact_extractor import (
    extract_facts_df_document_aware,
    write_facts_jsonl
)


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

    logger.info("STEP 1 -- Load document metadata")
    documents_options = effective_config.readers["bronze_documents"]
    documents_df = SparkReader(spark_session).read(**documents_options.options)

    logger.info("STEP 2 -- Build transient chunks")
    chunk_workset_df = create_chunk_workset(
        spark_session,
        documents_df,
        effective_config
    ).persist()

    try:
        logger.info("STEP 3 -- Write persisted chunk metadata")
        chunks_writer = effective_config.writers["silver_chunks"]
        SparkWriter(spark_session).write(
            select_persisted_chunk_columns(chunk_workset_df),
            **chunks_writer.options
        )

        logger.info("STEP 4 -- Extract governed facts")
        created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        facts_df = extract_facts_df_document_aware(spark_session, chunk_workset_df, created_at)
        facts_path = (
                effective_config.project_root
                / "runtime"
                / "metadata"
                / "facts"
                / "extracted_facts.jsonl"
        )
        write_facts_jsonl(
            [row.asDict(recursive=True) for row in facts_df.collect()],
            facts_path
        )
        facts_df.unpersist()

        logger.info("STEP 5 -- Generate encrypted embeddings")
        embeddings_df = generate_embeddings(
            spark_session,
            chunk_workset_df,
            effective_config
        )

        logger.info("STEP 6 -- Write encrypted embeddings")
        embeddings_writer = effective_config.writers["gold_embeddings"]
        SparkWriter(spark_session).write(
            embeddings_df,
            **embeddings_writer.options
        )
        embeddings_df.unpersist()

        logger.info("Gold write complete")
    finally:
        chunk_workset_df.unpersist()


if __name__ == "__main__":  # pragma: no cover
    main()
