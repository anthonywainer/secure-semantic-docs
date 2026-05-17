"""Local pipeline orchestrator for the secure semantic docs platform.

This module is a temporary local orchestrator structured to mirror the shape
of an Airflow DAG. Each task-like function corresponds to one pipeline step
that can be individually scheduled, monitored, and migrated to a real
orchestration engine later.

Run with:
    python -m secure_semantic_docs.demo
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from secure_semantic_docs.core import BaseSettings, ingest_log_execution, configure_logging
from secure_semantic_docs.loader import Config, load_config

logger = logging.getLogger(BaseSettings.APP_NAME)


@ingest_log_execution
def main() -> None:
    """Entry point for the local demo pipeline.

    Calls :func:`run_demo_pipeline` and exits with a non-zero code if any
    required task failed.
    """
    results = run_demo_pipeline()
    failed_required = [r for r in results if r.required and r.status == "failed"]
    if failed_required:
        sys.exit(1)


@dataclass
class TaskResult:
    """Result record for a single pipeline task."""

    name: str
    status: str
    required: bool
    duration_seconds: float
    error: str | None = None


def run_task(
        task_name: str,
        task_fn: Callable[[], Any],
        required: bool = True
) -> TaskResult:
    """Execute a single pipeline task and return its result.

    Parameters
    ----------
    task_name:
        Human-readable name used in log messages and result tracking.
    task_fn:
        Zero-argument callable implementing the task. May raise any exception.
    required:
        When True, a failure should stop the pipeline. When False, failure
        is logged as a warning and the pipeline continues.

    Returns
    -------
    TaskResult
        Populated with status, duration, and any error message.
    """
    logger.info("Starting task: %s", task_name)
    start = time.monotonic()
    try:
        task_fn()
        duration = time.monotonic() - start
        logger.info("Completed task: %s (%.2fs)", task_name, duration)
        return TaskResult(
            name=task_name,
            status="success",
            required=required,
            duration_seconds=round(duration, 3)
        )
    except Exception as exc:
        duration = time.monotonic() - start
        if required:
            logger.error("Failed required task: %s — %s", task_name, exc)
        else:
            logger.warning("Optional task skipped: %s — %s", task_name, exc)
        return TaskResult(
            name=task_name,
            status="failed",
            required=required,
            duration_seconds=round(duration, 3),
            error=str(exc)
        )


def task_prepare_runtime_dirs(config: Config) -> None:
    """Create required runtime output directories if they do not exist.

    Bronze, silver, and gold lakehouse directories plus logs and metadata
    directories must exist before any ingestion step can write output.
    """
    dirs = [
        config.lakehouse_dir,
        config.bronze_dir,
        config.lakehouse_dir / "silver_chunks",
        config.lakehouse_dir / "gold_embeddings",
        config.logs_dir,
        config.project_root / "runtime" / "metadata",
        config.project_root / "runtime" / "vector_store" / "chroma",
    ]
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=True)
    logger.debug("Runtime directories ready: %d created/verified", len(dirs))


def task_validate_configuration(config: Config) -> None:
    """Validate that the pipeline configuration is complete and coherent.

    Checks that the project root is resolvable and that the secret key
    environment variable name is set. Fails early rather than discovering
    configuration problems mid-run.
    """
    if not config.project_root.exists():
        raise RuntimeError(f"Project root does not exist: {config.project_root}")
    if not config.secret_key_env_var:
        raise RuntimeError("Secret key environment variable name is not configured.")
    logger.debug("Configuration valid — project root: %s", config.project_root)


def task_validate_input_data(config: Config) -> None:
    """Validate that required input data is available before ingestion.

    The raw documents directory must exist and contain at least one source
    file for bronze ingestion to proceed. An empty or missing directory is
    treated as a pipeline error.
    """
    raw_docs = config.raw_documents_dir
    if not raw_docs.exists():
        raise RuntimeError(f"Raw documents directory not found: {raw_docs}")
    doc_files = list(raw_docs.rglob("*.txt"))
    if not doc_files:
        raise RuntimeError(f"No .txt document files found under: {raw_docs}")
    logger.debug("Input data validated — %d source files found", len(doc_files))


def task_run_bronze_ingestion(_config: Config) -> None:
    """Run the bronze ingestion pipeline.

    Reads raw source documents and writes them to the bronze lakehouse layer.
    This is the first required step; all downstream steps depend on its output.
    """
    import secure_semantic_docs.bronze_ingestion as _bronze  # noqa: PLC0415
    _bronze.main()


def task_run_silver_ingestion(_config: Config) -> None:
    """Run the silver ingestion pipeline.

    Reads bronze records, applies chunking and metadata enrichment, and
    writes enriched chunks to the silver layer.
    """
    import secure_semantic_docs.silver_ingestion as _silver  # noqa: PLC0415
    _silver.main()


def task_run_gold_ingestion(_config: Config) -> None:
    """Run the gold ingestion pipeline.

    Generates encrypted embeddings from silver chunks and writes final chunk
    records with embeddings and permission metadata to the gold layer. Also
    extracts structured facts to a JSON Lines file.
    """
    import secure_semantic_docs.gold_ingestion as _gold  # noqa: PLC0415
    _gold.main()


def task_build_graph_or_facts(config: Config) -> None:
    """Load extracted facts and verify the graph/facts layer is populated.

    After gold ingestion, the fact store should contain structured records.
    This task loads and counts them to confirm the layer was built correctly.
    It is optional because the core search path works without a populated
    graph store.
    """
    from secure_semantic_docs.serving.retrieval_service import load_fact_records  # noqa: PLC0415
    facts_path = config.project_root / "runtime" / "metadata" / "facts" / "extracted_facts.jsonl"
    records = load_fact_records(facts_path)
    logger.info("Graph/facts layer contains %d fact record(s)", len(records))


def _decode_chroma_embeddings(
        config: Config,
        records: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[list[float]]]:
    """Return Chroma-ready records plus decrypted embedding vectors."""
    from secure_semantic_docs.embeddings.serializer import bytes_to_embedding  # noqa: PLC0415
    from secure_semantic_docs.security.keyring_store import resolve_secret_key  # noqa: PLC0415
    from secure_semantic_docs.security.secretbox_decryptor import secretbox_decrypt  # noqa: PLC0415

    encryption_key = resolve_secret_key(config)
    eligible_records: list[dict[str, Any]] = []
    embeddings: list[list[float]] = []

    for record in records:
        ciphertext = record.get("embedding_ciphertext")
        nonce = record.get("embedding_nonce")
        embedding_dim: int | None = record.get("embedding_dim")
        embedding_dtype = str(record.get("embedding_dtype") or "float32")

        if not isinstance(ciphertext, bytes | bytearray | memoryview):
            logger.warning("Skipping record without embedding ciphertext: %s", record.get("chunk_id"))
            continue
        if not isinstance(nonce, bytes | bytearray | memoryview):
            logger.warning("Skipping record without embedding nonce: %s", record.get("chunk_id"))
            continue
        if embedding_dim is None:
            logger.warning("Skipping record without embedding_dim: %s", record.get("chunk_id"))
            continue

        plaintext = secretbox_decrypt(bytes(ciphertext), bytes(nonce), encryption_key)
        vector = bytes_to_embedding(plaintext, int(embedding_dim), embedding_dtype)
        eligible_records.append(record)
        embeddings.append(vector.tolist())

    return eligible_records, embeddings


def task_sync_chroma_index(config: Config) -> None:
    """Synchronise the gold embeddings into the Chroma vector index.

    Reads gold records and upserts them into the running Chroma server.
    This step is optional because Chroma may not be available in all local
    development environments.
    """
    from secure_semantic_docs.governance.retrieval import load_gold_records  # noqa: PLC0415
    from secure_semantic_docs.vector_store.chroma_client import (  # noqa: PLC0415
        connect_chroma,
        upsert_candidates,
    )
    client = connect_chroma()
    gold_records = load_gold_records(config.lakehouse_dir / "gold_embeddings")
    if not gold_records:
        logger.warning("No gold records found — Chroma index not updated")
        return

    eligible_records, embeddings = _decode_chroma_embeddings(config, gold_records)
    if not eligible_records:
        logger.warning("No decryptable embeddings found — Chroma index not updated")
        return

    upserted = upsert_candidates(client, eligible_records, embeddings)
    logger.info("Chroma index synchronised — %d records upserted", upserted)


def task_export_openmetadata(config: Config) -> None:
    """Export the governance catalogue to an OpenMetadata-compatible JSON file.

    Writes asset metadata including lineage, contracts, and classifications
    to the logs directory. This step is optional and does not affect search.
    """
    from secure_semantic_docs.governance import export_openmetadata_catalog  # noqa: PLC0415
    output_path = config.logs_dir / "openmetadata_assets.json"
    export_openmetadata_catalog(output_path, config.project_root)
    logger.info("OpenMetadata catalog exported to %s", output_path)


def task_run_quality_checks(config: Config) -> None:
    """Run metadata quality checks across all lakehouse layers.

    Validates required fields, forbidden fields, and non-null constraints
    across bronze, silver, and gold tables. Writes a quality report to the
    logs directory. This step is optional and does not block serving.
    """
    from secure_semantic_docs.governance import (  # noqa: PLC0415
        validate_metadata_quality,
        write_quality_report,
    )
    report = validate_metadata_quality(
        config.bronze_dir,
        config.lakehouse_dir / "silver_chunks",
        config.lakehouse_dir / "gold_embeddings"
    )
    write_quality_report(report, config.logs_dir / "metadata_quality_report.json")
    status = report.get("status", "unknown")
    passed = report.get("passed", 0)
    total = report.get("total", 0)
    logger.info("Quality checks complete — %d/%d passed (status: %s)", passed, total, status)
    for warning in report.get("warnings", []):
        logger.warning("Quality warning: %s", warning)


def run_demo_pipeline() -> list[TaskResult]:
    """Orchestrate the full local processing pipeline.

    Runs required steps in order, stopping on the first required failure.
    Optional steps are attempted after all required steps succeed and are
    skipped gracefully on error.

    Returns
    -------
    list[TaskResult]
        One result per attempted task, in execution order.
    """
    configure_logging()
    config = load_config()
    results: list[TaskResult] = []

    required_steps: list[tuple[str, Callable[[], Any]]] = [
        ("prepare_runtime_dirs", lambda: task_prepare_runtime_dirs(config)),
        ("validate_configuration", lambda: task_validate_configuration(config)),
        ("validate_input_data", lambda: task_validate_input_data(config)),
        ("bronze_ingestion", lambda: task_run_bronze_ingestion(config)),
        ("silver_ingestion", lambda: task_run_silver_ingestion(config)),
        ("gold_ingestion", lambda: task_run_gold_ingestion(config)),
    ]

    optional_steps: list[tuple[str, Callable[[], Any]]] = [
        ("build_graph_or_facts", lambda: task_build_graph_or_facts(config)),
        ("sync_chroma_index", lambda: task_sync_chroma_index(config)),
        ("export_openmetadata", lambda: task_export_openmetadata(config)),
        ("quality_checks", lambda: task_run_quality_checks(config)),
    ]

    for name, fn in required_steps:
        result = run_task(name, fn, required=True)
        results.append(result)
        if result.status == "failed":
            logger.error("Pipeline aborted after required task failure: %s", name)
            return results

    for name, fn in optional_steps:
        results.append(run_task(name, fn, required=False))

    successful = sum(1 for r in results if r.status == "success")
    logger.info("Pipeline complete — %d/%d tasks succeeded", successful, len(results))
    return results


if __name__ == "__main__":  # pragma: no cover
    main()
