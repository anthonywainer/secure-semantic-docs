# Future Airflow Integration

## Status

**NOT YET IMPLEMENTED.**

The local pipeline (`demo.py`) is intentionally structured to mirror an Airflow DAG.
Each task-like function corresponds to one pipeline step and can be lifted into an Airflow
`PythonOperator` or `@task` without significant rework.

## Current local orchestrator

`src/secure_semantic_docs/demo.py` runs the full pipeline locally:

```bash
python -m secure_semantic_docs.demo
```

The pipeline runs these steps in order:

| Step                        | Task function                 | Required |
|-----------------------------|-------------------------------|----------|
| Prepare runtime directories | `task_prepare_runtime_dirs`   | Yes      |
| Validate configuration      | `task_validate_configuration` | Yes      |
| Validate input data         | `task_validate_input_data`    | Yes      |
| Bronze ingestion            | `task_run_bronze_ingestion`   | Yes      |
| Silver ingestion            | `task_run_silver_ingestion`   | Yes      |
| Gold ingestion              | `task_run_gold_ingestion`     | Yes      |
| Build graph / facts         | `task_build_graph_or_facts`   | No       |
| Sync Chroma index           | `task_sync_chroma_index`      | No       |
| Export OpenMetadata         | `task_export_openmetadata`    | No       |
| Quality checks              | `task_run_quality_checks`     | No       |

Required tasks stop the pipeline on failure. Optional tasks are logged and skipped.

## Mapping to an Airflow DAG

Each task function in `demo.py` maps directly to a `@task` decorated callable in Airflow.
The `Config` object becomes the Airflow `params` dict or a `Variable`-backed config loader.

### Minimal DAG sketch

```python
from __future__ import annotations

from datetime import datetime

from airflow.decorators import dag, task
from airflow.models import Variable

from secure_semantic_docs.loader import load_config


@dag(
    dag_id="secure_semantic_docs_pipeline",
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["secure-semantic-docs", "medallion"],
)
def pipeline() -> None:
    """Medallion ingestion pipeline for Secure Semantic Docs."""

    @task
    def prepare_runtime_dirs() -> None:
        from secure_semantic_docs.demo import task_prepare_runtime_dirs
        task_prepare_runtime_dirs(load_config())

    @task
    def validate_configuration() -> None:
        from secure_semantic_docs.demo import task_validate_configuration
        task_validate_configuration(load_config())

    @task
    def validate_input_data() -> None:
        from secure_semantic_docs.demo import task_validate_input_data
        task_validate_input_data(load_config())

    @task
    def bronze_ingestion() -> None:
        from secure_semantic_docs.demo import task_run_bronze_ingestion
        task_run_bronze_ingestion(load_config())

    @task
    def silver_ingestion() -> None:
        from secure_semantic_docs.demo import task_run_silver_ingestion
        task_run_silver_ingestion(load_config())

    @task
    def gold_ingestion() -> None:
        from secure_semantic_docs.demo import task_run_gold_ingestion
        task_run_gold_ingestion(load_config())

    @task(trigger_rule="all_success")
    def build_graph_or_facts() -> None:
        from secure_semantic_docs.demo import task_build_graph_or_facts
        task_build_graph_or_facts(load_config())

    @task(trigger_rule="all_success")
    def sync_chroma_index() -> None:
        from secure_semantic_docs.demo import task_sync_chroma_index
        task_sync_chroma_index(load_config())

    @task(trigger_rule="all_success")
    def export_openmetadata() -> None:
        from secure_semantic_docs.demo import task_export_openmetadata
        task_export_openmetadata(load_config())

    @task(trigger_rule="all_success")
    def quality_checks() -> None:
        from secure_semantic_docs.demo import task_run_quality_checks
        task_run_quality_checks(load_config())

    # Dependencies
    dirs = prepare_runtime_dirs()
    cfg = validate_configuration()
    data = validate_input_data()

    dirs >> cfg >> data

    bronze = bronze_ingestion()
    data >> bronze

    silver = silver_ingestion()
    bronze >> silver

    gold = gold_ingestion()
    silver >> gold

    # Optional downstream tasks — all depend on gold succeeding
    gold >> [build_graph_or_facts(), sync_chroma_index(), export_openmetadata(), quality_checks()]


pipeline()
```

### Recommended DAG placement

Place the DAG file under `dags/` at the project root:

```
dags/
└── pipeline.py
```

Airflow discovers DAGs by scanning the `dags/` directory configured in `airflow.cfg`.

## Required environment variables

| Variable                            | Description                                             |
|-------------------------------------|---------------------------------------------------------|
| `SECURE_SEMANTIC_DOCS_SECRET_KEY`   | Symmetric encryption key (base64) for PyNaCl            |
| `SECURE_SEMANTIC_DOCS_PROJECT_ROOT` | Absolute path to the project root on the Airflow worker |
| `AIRFLOW__CORE__DAGS_FOLDER`        | Path to the `dags/` directory                           |

Inject all secrets through Airflow Connections or the Secrets Backend. Never store them
in DAG source files or Airflow Variables in plain text.

## Spark on Airflow

For PySpark steps, use the `SparkSubmitOperator` or run the tasks on a Spark-enabled worker
with a pre-configured `SPARK_HOME`. The task functions call `get_or_create_spark_session()`
internally, which reuses an existing session if one is already active.

When running Spark remotely (e.g., on a Dataproc or EMR cluster), replace the local
`SparkSession` builder with a `SparkSubmitOperator` that submits each ingestion module
as a standalone Spark job:

```python
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

bronze = SparkSubmitOperator(
    task_id="bronze_ingestion",
    application="src/secure_semantic_docs/bronze_ingestion.py",
    conn_id="spark_default",
    verbose=False,
)
```

## Security requirements on Airflow workers

- Workers must have access to the encryption key via the configured environment variable.
- The `runtime/` directory must be on a shared or distributed file system accessible by all workers.
- Audit logs written by the pipeline must be persisted to durable storage.
- Do not pass encryption keys as DAG parameters or log them in task logs.

## Why demo.py is not removed when Airflow is added

`demo.py` remains useful for local development, CI, and debugging without a full Airflow
deployment. Airflow and the local orchestrator share the same underlying task functions,
so both paths stay in sync automatically when task logic changes.
