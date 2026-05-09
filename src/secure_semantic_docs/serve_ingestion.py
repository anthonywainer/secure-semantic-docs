import logging

from secure_semantic_docs.core import ingest_log_execution, configure_logging, BaseSettings
from secure_semantic_docs.core.spark import build_spark_session
from secure_semantic_docs.io import SparkReader
from secure_semantic_docs.loader import load_config


@ingest_log_execution
def main() -> None:
    """Entry point: configure logging, build Spark, then run :func:`ingest`."""
    logging.getLogger("py4j").setLevel(logging.ERROR)
    configure_logging()
    pipeline_config = load_config()
    spark_session = build_spark_session(pipeline_config)
    ingest(spark_session, pipeline_config)


def ingest(spark_session, pipeline_config):
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

    logger.info("STEP 1 -- Load gold documents")
    gold_documents_options = effective_config.readers["gold_documents"]
    gold_documents_df = SparkReader(spark_session).read(**gold_documents_options.options)

    logger.info("STEP 2 -- Building Chroma vector store")
    _upsert_to_vector_store(gold_documents_df, pipeline_config)
    collection = create_or_load_collection(config)
    logger.info("Vector store ready with %d vectors", collection.count())


def _upsert_to_vector_store(gold_df: DataFrame, config: Config) -> None:
    """Upsert gold embeddings to Chroma via ``coalesce(1).foreachPartition``.

    No data is collected to the driver.  The Chroma client is created once
    inside the single partition so there are no concurrency issues.
    Sensitive ``chunk_text`` is encrypted inside the partition before the
    metadata is written to Chroma.
    """
    chroma_dir = str(config.chroma_dir)
    collection_name = config.chroma_collection_name
    doc_meta_json = (config.metadata_dir / "documents_metadata.json").read_text(
        encoding="utf-8"
    )
    enc_key: bytes = load_or_create_local_key(config)

    def _partition_fn(rows: Iterator[Row]) -> None:
        import json as _json
        import logging as _logging

        import chromadb
        from secure_semantic_docs.security.encryption import encrypt_sensitive_fields

        _log = _logging.getLogger(__name__)
        doc_meta: dict[str, Any] = {
            str(r["document_id"]): r for r in _json.loads(doc_meta_json)
        }

        client = chromadb.PersistentClient(path=chroma_dir)
        collection = client.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine"}
        )

        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict[str, Any]] = []
        embs: list[list[float]] = []

        for row in rows:
            d = row.asDict()
            title = str(doc_meta.get(str(d["document_id"]), {}).get("title", ""))
            chunk = {**d, "title": title}
            chunk = encrypt_sensitive_fields(chunk, enc_key)

            allowed_roles = list(chunk.get("allowed_roles") or [])
            ids.append(str(chunk["chunk_id"]))
            docs.append(str(chunk.get("chunk_text", "") or ""))
            metas.append(
                {
                    "chunk_id": str(chunk["chunk_id"]),
                    "document_id": str(chunk["document_id"]),
                    "title": title,
                    "classification": str(chunk.get("classification", "")),
                    "allowed_roles": ",".join(str(r) for r in allowed_roles),
                    "owner": str(chunk.get("owner", "")),
                    "department": str(chunk.get("department", "")),
                    "version": str(chunk.get("version", "")),
                    "sensitivity_score": float(
                        chunk.get("sensitivity_score", 0.0) or 0.0
                    ),
                    "source_path": str(chunk.get("source_path", ""))
                }
            )
            embs.append(list(d["embedding"]))

        if not ids:
            return

        batch_size = 500
        for start in range(0, len(ids), batch_size):
            end = start + batch_size
            collection.upsert(
                ids=ids[start:end],
                documents=docs[start:end],
                metadatas=metas[start:end],
                embeddings=embs[start:end]
            )
        _log.info("Upserted %d chunks to vector store partition", len(ids))

    gold_df.coalesce(1).foreachPartition(_partition_fn)

