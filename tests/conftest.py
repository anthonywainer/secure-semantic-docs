"""Shared pytest fixtures for secure-semantic-docs test suite."""

import os
import shutil
import sys
from pathlib import Path

import pytest

from secure_semantic_docs.loader import Config

os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)


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


@pytest.fixture
def seeded_demo_data(tmp_path: Path) -> Path:
    """Copy demo input data into a temporary project root."""
    source_dir = Path(__file__).resolve().parents[1] / "data" / "synthetic_data"
    destination_dir = tmp_path / "data" / "synthetic_data"
    if not destination_dir.exists():
        shutil.copytree(source_dir, destination_dir)
    return destination_dir
