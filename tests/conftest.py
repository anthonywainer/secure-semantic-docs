"""Shared pytest fixtures for secure-semantic-docs test suite."""

import pytest

from secure_semantic_docs.config import Config, PipelineConfig


@pytest.fixture(scope="session")
def spark():
    """Provide a minimal SparkSession for tests that require Spark.

    Scoped to the session so Spark is started only once per test run.
    Tests using this fixture are automatically slow -- mark them with
    ``@pytest.mark.integration`` to exclude from fast runs.
    """
    from pyspark.sql import SparkSession

    session = (
        SparkSession.builder.master("local[1]")
        .appName("docsec-tests")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.driver.memory", "512m")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


@pytest.fixture
def config(tmp_path):
    """Return a Config pointing at a temporary directory."""
    return Config(
        project_root=tmp_path,
        pipeline=PipelineConfig(chunk_size=50, chunk_overlap=10, default_top_k=3)
    )


@pytest.fixture
def sample_chunk():
    """Return a minimal chunk dict with all required fields."""
    return {
        "chunk_id": "chunk-001",
        "document_id": "DOC-001",
        "chunk_text": "This is a sample chunk for testing.",
        "classification": "internal",
        "allowed_roles": ["data_engineer"],
        "owner": "Alice",
        "department": "Engineering",
        "version": "1.0",
        "source_path": "data/raw_documents/internal/DOC-001.txt",
        "document_hash": "abc123",
        "sensitivity_score": 0.1,
        "requires_encryption": False,
        "requires_restricted_access": False,
        "detected_sensitive_types": []
    }


@pytest.fixture
def users():
    """Return a dict of representative test users keyed by user_id."""
    return {
        "USR-001": {
            "user_id": "USR-001",
            "name": "Alice",
            "role": "data_engineer",
            "department": "Data Platform",
            "clearance_level": "internal"
        },
        "USR-002": {
            "user_id": "USR-002",
            "name": "Bob",
            "role": "business_analyst",
            "department": "Finance",
            "clearance_level": "internal"
        },
        "USR-003": {
            "user_id": "USR-003",
            "name": "Carol",
            "role": "security_engineer",
            "department": "Security",
            "clearance_level": "confidential"
        },
        "USR-004": {
            "user_id": "USR-004",
            "name": "David",
            "role": "finance_manager",
            "department": "Finance",
            "clearance_level": "restricted"
        },
        "USR-005": {
            "user_id": "USR-005",
            "name": "Eve",
            "role": "external_viewer",
            "department": "External",
            "clearance_level": "public"
        }
    }
