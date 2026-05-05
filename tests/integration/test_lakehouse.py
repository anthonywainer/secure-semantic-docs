"""Integration and unit tests for the lakehouse read/write layer."""

from unittest.mock import MagicMock, patch

import pytest
from pyspark.sql.types import StringType, StructField, StructType

from secure_semantic_docs.config import IcebergConfig, load_config
from secure_semantic_docs.config._schema import Config
from secure_semantic_docs.exceptions import IngestionError
from secure_semantic_docs.storage.lakehouse import (
    _ensure_namespace,
    _iceberg_table_id,
    _read_iceberg,
    _write_iceberg,
    read_bronze,
    read_gold,
    read_layer,
    read_silver,
    write_layer,
)


_SIMPLE_SCHEMA = StructType([StructField("id", StringType(), True)])


class TestIcebergTableId:
    def test_bronze_documents(self):
        ic = IcebergConfig(catalog_name="local")
        assert _iceberg_table_id(ic, "bronze_documents") == "local.bronze.documents"

    def test_silver_chunks(self):
        ic = IcebergConfig(catalog_name="local")
        assert _iceberg_table_id(ic, "silver_chunks") == "local.silver.chunks"

    def test_gold_embeddings(self):
        ic = IcebergConfig(catalog_name="local")
        assert _iceberg_table_id(ic, "gold_embeddings") == "local.gold.embeddings"

    def test_custom_catalog_name(self):
        ic = IcebergConfig(catalog_name="prod_catalog")
        assert (
            _iceberg_table_id(ic, "bronze_documents") == "prod_catalog.bronze.documents"
        )

    def test_unknown_name_raises_value_error(self):
        ic = IcebergConfig(catalog_name="local")
        with pytest.raises(ValueError, match="Unknown logical table name 'bad_name'"):
            _iceberg_table_id(ic, "bad_name")


class TestEnsureNamespace:
    def test_creates_bronze_namespace(self):
        spark_mock = MagicMock()
        ic = IcebergConfig(catalog_name="local")
        _ensure_namespace(spark_mock, ic, "bronze_documents")
        spark_mock.sql.assert_called_once_with(
            "CREATE NAMESPACE IF NOT EXISTS local.bronze"
        )

    def test_creates_silver_namespace(self):
        spark_mock = MagicMock()
        ic = IcebergConfig(catalog_name="mycat")
        _ensure_namespace(spark_mock, ic, "silver_chunks")
        spark_mock.sql.assert_called_once_with(
            "CREATE NAMESPACE IF NOT EXISTS mycat.silver"
        )

    def test_creates_gold_namespace(self):
        spark_mock = MagicMock()
        ic = IcebergConfig(catalog_name="local")
        _ensure_namespace(spark_mock, ic, "gold_embeddings")
        spark_mock.sql.assert_called_once_with(
            "CREATE NAMESPACE IF NOT EXISTS local.gold"
        )


class TestWriteIceberg:
    def test_calls_ensure_namespace_and_write_to(self, tmp_path):
        df_mock = MagicMock()
        spark_mock = MagicMock()
        cfg = Config(
            project_root=tmp_path,
            iceberg=IcebergConfig(enabled=True, catalog_name="local"),
        )
        _write_iceberg(df_mock, "bronze_documents", spark_mock, cfg)
        spark_mock.sql.assert_called_once()
        df_mock.writeTo.assert_called_once_with("local.bronze.documents")


class TestReadIceberg:
    def test_calls_spark_table(self, tmp_path):
        spark_mock = MagicMock()
        expected_df = MagicMock()
        spark_mock.table.return_value = expected_df
        cfg = Config(
            project_root=tmp_path,
            iceberg=IcebergConfig(enabled=True, catalog_name="local"),
        )
        result = _read_iceberg(spark_mock, "bronze_documents", cfg)
        spark_mock.table.assert_called_once_with("local.bronze.documents")
        assert result is expected_df


@pytest.mark.integration
class TestWriteLayer:
    def test_parquet_mode_writes_directory(self, spark, config):
        df = spark.createDataFrame([("row1",)], schema=_SIMPLE_SCHEMA)
        write_layer(df, "bronze_documents", config.bronze_dir, config)
        assert config.bronze_dir.exists()
        assert any(config.bronze_dir.glob("*.parquet"))

    def test_parquet_mode_uses_config_compression(self, spark, config):
        df = spark.createDataFrame([("row1",)], schema=_SIMPLE_SCHEMA)
        write_layer(df, "bronze_documents", config.bronze_dir, config)
        assert config.bronze_dir.exists()

    def test_iceberg_mode_calls_write_iceberg(self, spark, config):
        df = spark.createDataFrame([("row1",)], schema=_SIMPLE_SCHEMA)
        ic_cfg = Config(
            project_root=config.project_root,
            iceberg=IcebergConfig(enabled=True, catalog_name="local"),
        )
        with patch("secure_semantic_docs.storage.lakehouse._write_iceberg") as mock_wi:
            write_layer(df, "bronze_documents", config.bronze_dir, ic_cfg, spark)
            mock_wi.assert_called_once()

    def test_spark_fallback_from_df_session(self, spark, config):
        df = spark.createDataFrame([("row1",)], schema=_SIMPLE_SCHEMA)
        ic_cfg = Config(
            project_root=config.project_root,
            iceberg=IcebergConfig(enabled=True, catalog_name="local"),
        )
        with patch("secure_semantic_docs.storage.lakehouse._write_iceberg") as mock_wi:
            write_layer(df, "bronze_documents", config.bronze_dir, ic_cfg)
            mock_wi.assert_called_once()

    def test_uses_load_config_when_none(self, spark, config, monkeypatch, tmp_path):
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        cfg = load_config(project_root=tmp_path)
        df = spark.createDataFrame([("row1",)], schema=_SIMPLE_SCHEMA)
        write_layer(df, "bronze_documents", cfg.bronze_dir, cfg)
        assert cfg.bronze_dir.exists()


@pytest.mark.integration
class TestReadLayer:
    def test_parquet_reads_written_data(self, spark, config):
        df = spark.createDataFrame([("hello",)], schema=_SIMPLE_SCHEMA)
        write_layer(df, "bronze_documents", config.bronze_dir, config)
        result = read_layer(spark, "bronze_documents", config.bronze_dir, config=config)
        assert result.count() == 1
        assert result.first()["id"] == "hello"

    def test_parquet_missing_dir_raises_ingestion_error(self, spark, config):
        with pytest.raises(IngestionError, match="Bronze"):
            read_layer(
                spark,
                "bronze_documents",
                config.bronze_dir,
                layer_name="Bronze",
                config=config,
            )

    def test_parquet_with_explicit_schema(self, spark, config):
        df = spark.createDataFrame([("val",)], schema=_SIMPLE_SCHEMA)
        write_layer(df, "bronze_documents", config.bronze_dir, config)
        result = read_layer(
            spark,
            "bronze_documents",
            config.bronze_dir,
            schema=_SIMPLE_SCHEMA,
            config=config,
        )
        assert result.count() == 1

    def test_iceberg_mode_calls_read_iceberg(self, spark, config):
        mock_df = MagicMock()
        ic_cfg = Config(
            project_root=config.project_root,
            iceberg=IcebergConfig(enabled=True, catalog_name="local"),
        )
        with patch(
            "secure_semantic_docs.storage.lakehouse._read_iceberg", return_value=mock_df
        ) as mock_ri:
            result = read_layer(
                spark, "bronze_documents", config.bronze_dir, config=ic_cfg
            )
            mock_ri.assert_called_once()
            assert result is mock_df

    def test_uses_load_config_when_none(self, spark, tmp_path, monkeypatch):
        cfg = load_config(project_root=tmp_path)
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        df = spark.createDataFrame([("row1",)], schema=_SIMPLE_SCHEMA)
        write_layer(df, "bronze_documents", cfg.bronze_dir, cfg)
        result = read_layer(spark, "bronze_documents", cfg.bronze_dir)
        assert result.count() == 1


@pytest.mark.integration
class TestReadBronze:
    def test_returns_dataframe(self, spark, tmp_path):
        from secure_semantic_docs.synthetic import save_dataset
        from secure_semantic_docs.pipeline.bronze import ingest_documents

        cfg = load_config(project_root=tmp_path)
        save_dataset(cfg)
        ingest_documents(spark, cfg)
        result = read_bronze(spark, cfg)
        assert result.count() == 25

    def test_uses_load_config_when_none(self, spark, tmp_path, monkeypatch):
        from secure_semantic_docs.synthetic import save_dataset
        from secure_semantic_docs.pipeline.bronze import ingest_documents

        cfg = load_config(project_root=tmp_path)
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        save_dataset(cfg)
        ingest_documents(spark, cfg)
        result = read_bronze(spark)
        assert result.count() == 25


@pytest.mark.integration
class TestReadSilver:
    def test_raises_when_silver_not_written(self, spark, config):
        with pytest.raises(IngestionError, match="Silver"):
            read_silver(spark, config)

    def test_uses_load_config_when_none(self, spark, tmp_path, monkeypatch):
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        cfg = load_config(project_root=tmp_path)
        with pytest.raises(IngestionError, match="Silver"):
            read_silver(spark, cfg)


@pytest.mark.integration
class TestReadGold:
    def test_raises_when_gold_not_written(self, spark, config):
        with pytest.raises(IngestionError, match="Gold"):
            read_gold(spark, config)

    def test_uses_load_config_when_none(self, spark, tmp_path, monkeypatch):
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        cfg = load_config(project_root=tmp_path)
        with pytest.raises(IngestionError, match="Gold"):
            read_gold(spark, cfg)
