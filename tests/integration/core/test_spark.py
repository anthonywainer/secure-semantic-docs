"""Integration tests for the Spark session factory."""

import pytest
from pyspark.sql import SparkSession

from secure_semantic_docs.core.spark import (
    iceberg_confs,
    merge_configurations,
    build_spark_session
)
from secure_semantic_docs.loader import Config
from secure_semantic_docs.loader import IcebergConfig


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
        cfg = Config(  # type: ignore[misc]
            project_root=tmp_path,
            iceberg=IcebergConfig(enabled=True, catalog_name="local")
        )
        session = build_spark_session(cfg)
        assert isinstance(session, SparkSession)


class TestSparkConfs:
    def test_confs_contains_required_keys(self, tmp_path):
        from secure_semantic_docs.loader import load_config

        cfg = load_config(project_root=tmp_path)
        confs = cfg.spark.confs
        assert "spark.master" in confs
        assert "spark.app.name" in confs
        assert "spark.sql.shuffle.partitions" in confs
        assert "spark.driver.memory" in confs
        assert "spark.executor.memory" in confs

    def test_confs_values_match_yaml(self, tmp_path):
        from secure_semantic_docs.loader import load_config

        cfg = load_config(project_root=tmp_path)
        confs = cfg.spark.confs
        assert confs["spark.master"] == "local[*]"
        assert confs["spark.app.name"] == "DocSecPipeline"

    def test_managed_true_confs_not_applied(self, tmp_path):
        from secure_semantic_docs.models.spark_models import SparkConfig

        cfg = Config(project_root=tmp_path, spark=SparkConfig(managed=True))  # type: ignore[misc]
        assert cfg.spark.managed is True
        assert cfg.spark.confs == {}

    def test_empty_string_values_excluded_from_confs(self, tmp_path):
        from secure_semantic_docs.models.spark_models import SparkConfig

        cfg = Config(  # type: ignore[misc]
            project_root=tmp_path,
            spark=SparkConfig(confs={"spark.jars.packages": "org.apache:pkg:1.0"})
        )
        assert cfg.spark.confs["spark.jars.packages"] == "org.apache:pkg:1.0"


class TestIcebergConfs:
    @staticmethod
    def _make_ic(**kwargs) -> IcebergConfig:
        defaults = {
            "enabled": True,
            "catalog_name": "local",
            "catalog_type": "rest",
            "catalog_uri": "http://localhost:8181",
            "warehouse": "/tmp/warehouse"
        }
        return IcebergConfig(**{**defaults, **kwargs})

    def test_contains_extensions_key(self):
        confs = dict(iceberg_confs(self._make_ic()))
        assert "spark.sql.extensions" in confs

    def test_contains_catalog_keys(self):
        confs = dict(iceberg_confs(self._make_ic(catalog_name="mycat")))
        assert "spark.sql.catalog.mycat" in confs
        assert "spark.sql.catalog.mycat.type" in confs
        assert "spark.sql.catalog.mycat.warehouse" in confs

    def test_rest_catalog_adds_uri(self):
        confs = dict(iceberg_confs(self._make_ic(catalog_type="rest")))
        assert "spark.sql.catalog.local.uri" in confs

    def test_hadoop_catalog_no_uri(self):
        confs = dict(iceberg_confs(self._make_ic(catalog_type="hadoop")))
        assert "spark.sql.catalog.local.uri" not in confs

    def test_no_jar_keys_in_iceberg_confs(self):
        confs = dict(iceberg_confs(self._make_ic()))
        assert "spark.jars" not in confs
        assert "spark.jars.packages" not in confs


class TestMergeConfigurations:
    def test_deduplicates_by_last_write(self):
        result = dict(merge_configurations([("a", "1"), ("b", "2"), ("a", "3")]))
        assert result["a"] == "1,3"
        assert result["b"] == "2"

    def test_unique_keys_unchanged(self):
        result = dict(merge_configurations([("x", "foo"), ("y", "bar")]))
        assert result == {"x": "foo", "y": "bar"}

    def test_empty_input(self):
        assert merge_configurations([]) == []
