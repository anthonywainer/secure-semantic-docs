"""Shared pytest fixtures for secure-semantic-docs test suite."""

import pytest

from secure_semantic_docs.loader import Config


@pytest.fixture(scope="session")
def spark():
    """Provide a minimal SparkSession for tests that require Spark.

    Scoped to the session so Spark is started only once per test run.
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
    return Config(project_root=tmp_path)
