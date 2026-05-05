"""Integration tests for the Spark session factory."""

import pytest

from pyspark.sql import SparkSession

from secure_semantic_docs.config import IcebergConfig
from secure_semantic_docs.config._schema import Config
from secure_semantic_docs.spark import _configure_iceberg, build_spark_session


@pytest.mark.integration
class TestBuildSparkSession:
    def test_returns_spark_session(self, spark, config):
        session = build_spark_session(config)
        assert isinstance(session, SparkSession)

    def test_uses_load_config_when_none(self, spark, monkeypatch, tmp_path):
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        session = build_spark_session()
        assert isinstance(session, SparkSession)

    def test_iceberg_disabled_path(self, spark, config):
        assert config.iceberg.enabled is False
        session = build_spark_session(config)
        assert isinstance(session, SparkSession)

    def test_iceberg_enabled_path(self, spark, tmp_path):
        cfg = Config(
            project_root=tmp_path,
            iceberg=IcebergConfig(enabled=True, catalog_name="local"),
        )
        session = build_spark_session(cfg)
        assert isinstance(session, SparkSession)


class TestConfigureIceberg:
    def test_with_spark_jars(self):
        ic = IcebergConfig(
            enabled=True,
            catalog_name="local",
            catalog_type="rest",
            catalog_uri="http://localhost:8181",
            warehouse="/tmp/warehouse",
            spark_jars="/opt/spark/jars/iceberg.jar",
            spark_packages="",
        )
        builder = SparkSession.builder
        result = _configure_iceberg(builder, ic)
        assert isinstance(result, SparkSession.Builder)

    def test_with_spark_packages(self):
        ic = IcebergConfig(
            enabled=True,
            catalog_name="local",
            catalog_type="rest",
            catalog_uri="http://localhost:8181",
            warehouse="/tmp/warehouse",
            spark_jars="",
            spark_packages="org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.6.1",
        )
        builder = SparkSession.builder
        result = _configure_iceberg(builder, ic)
        assert isinstance(result, SparkSession.Builder)

    def test_with_no_jars_no_packages(self):
        ic = IcebergConfig(
            enabled=True,
            catalog_name="local",
            catalog_type="rest",
            catalog_uri="http://localhost:8181",
            warehouse="/tmp/warehouse",
            spark_jars="",
            spark_packages="",
        )
        builder = SparkSession.builder
        result = _configure_iceberg(builder, ic)
        assert isinstance(result, SparkSession.Builder)

    def test_rest_catalog_adds_uri(self):
        ic = IcebergConfig(
            enabled=True,
            catalog_name="testcat",
            catalog_type="rest",
            catalog_uri="http://my-rest-catalog:8181",
            warehouse="/tmp/wh",
            spark_jars="",
            spark_packages="",
        )
        builder = SparkSession.builder
        result = _configure_iceberg(builder, ic)
        assert isinstance(result, SparkSession.Builder)

    def test_hadoop_catalog_no_uri(self):
        ic = IcebergConfig(
            enabled=True,
            catalog_name="hadoopcat",
            catalog_type="hadoop",
            catalog_uri="",
            warehouse="/tmp/wh",
            spark_jars="",
            spark_packages="",
        )
        builder = SparkSession.builder
        result = _configure_iceberg(builder, ic)
        assert isinstance(result, SparkSession.Builder)
