"""Unit tests for core utilities: banner, execution, logging, and spark."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from secure_semantic_docs.core.execution import ingest_log_execution
from secure_semantic_docs.core.logging import configure_logging
from secure_semantic_docs.core.project_metadata import load_project_metadata
from secure_semantic_docs.core.spark import build_spark_session
from secure_semantic_docs.loader import Config
from secure_semantic_docs.models.spark_models import IcebergConfig, SparkConfig


class TestIngestLogExecution:
    def test_success_returns_result(self):
        @ingest_log_execution
        def fn():
            return 42

        assert fn() == 42

    def test_failure_reraises(self):
        @ingest_log_execution
        def fn():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            fn()

    def test_logs_on_success(self, caplog):
        @ingest_log_execution
        def fn():
            return "ok"

        with caplog.at_level(logging.INFO):
            fn()

        assert any("finished" in r.message.lower() for r in caplog.records)

    def test_logs_on_failure(self, caplog):
        @ingest_log_execution
        def fn():
            raise RuntimeError("fail")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(RuntimeError):
                fn()

        assert any("failed" in r.message.lower() for r in caplog.records)


class TestConfigureLogging:
    @staticmethod
    def setup_method():
        from secure_semantic_docs.core.logging import reset_banner

        reset_banner()

    def test_default_ini_configures_logging(self):
        configure_logging()
        assert logging.getLogger("DocSecPipeline") is not None

    def test_custom_ini_path_used(self, tmp_path):
        ini = tmp_path / "test_logging.ini"
        ini.write_text(
            "[loggers]\nkeys=root\n"
            "[handlers]\nkeys=consoleHandler\n"
            "[formatters]\nkeys=simpleFormatter\n"
            "[logger_root]\nlevel=DEBUG\nhandlers=consoleHandler\n"
            "[handler_consoleHandler]\nclass=StreamHandler\nlevel=DEBUG\n"
            "formatter=simpleFormatter\nargs=(sys.stdout,)\n"
            "[formatter_simpleFormatter]\nformat=%(message)s\n"
        )
        configure_logging(ini_path=ini)
        assert logging.getLogger().level == logging.DEBUG

    def test_banner_logged_once_for_app_logger(self):
        with (
            patch("secure_semantic_docs.core.logging.build_banner", return_value="banner"),
            patch("secure_semantic_docs.core.logging.logging.getLogger") as mock_get_logger
        ):
            logger = MagicMock()
            mock_get_logger.return_value = logger

            configure_logging()
            configure_logging()

        logger.info.assert_called_once_with("\n%s", "banner")


class TestProjectMetadata:
    def test_load_project_metadata_reads_pyproject(self):
        metadata = load_project_metadata()

        assert metadata.name == "secure-semantic-docs"
        assert metadata.version == "0.3.0"
        assert metadata.author == "AnthonyWainer"


class TestBuildSparkSessionUnit:
    @staticmethod
    def _cfg(tmp_path, **kwargs) -> Config:
        return Config(project_root=tmp_path, **kwargs)  # type: ignore[misc]

    @staticmethod
    def _patches():
        return (
            patch("secure_semantic_docs.core.spark.SparkSession"),
            patch("secure_semantic_docs.core.spark.SparkConf")
        )

    def test_no_config_calls_load_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        mock_session = MagicMock()
        with (
            patch("secure_semantic_docs.core.spark.SparkSession") as ms,
            patch("secure_semantic_docs.core.spark.SparkConf")
        ):
            ms.getActiveSession.return_value = None
            ms.builder.config.return_value.getOrCreate.return_value = mock_session
            result = build_spark_session()
        assert result == mock_session

    def test_managed_true_sets_empty_confs(self, tmp_path):
        cfg = self._cfg(tmp_path, spark=SparkConfig(managed=True))
        with (
            patch("secure_semantic_docs.core.spark.SparkSession") as ms,
            patch("secure_semantic_docs.core.spark.SparkConf") as mc
        ):
            ms.getActiveSession.return_value = None
            ms.builder.config.return_value.getOrCreate.return_value = MagicMock()
            build_spark_session(cfg)
        mc.return_value.setAll.assert_called_once_with([])

    def test_iceberg_enabled_appends_confs(self, tmp_path):
        cfg = self._cfg(
            tmp_path,
            iceberg=IcebergConfig(
                enabled=True,
                catalog_name="local",
                catalog_type="rest",
                catalog_uri="http://localhost:8181",
                warehouse="/tmp/wh"
            )
        )
        with (
            patch("secure_semantic_docs.core.spark.SparkSession") as ms,
            patch("secure_semantic_docs.core.spark.SparkConf") as mc
        ):
            ms.getActiveSession.return_value = None
            ms.builder.config.return_value.getOrCreate.return_value = MagicMock()
            build_spark_session(cfg)
        keys = [k for k, _ in mc.return_value.setAll.call_args[0][0]]
        assert "spark.sql.extensions" in keys

    def test_session_log_level_set(self, tmp_path):
        cfg = self._cfg(tmp_path)
        mock_session = MagicMock()
        with (
            patch("secure_semantic_docs.core.spark.SparkSession") as ms,
            patch("secure_semantic_docs.core.spark.SparkConf")
        ):
            ms.getActiveSession.return_value = None
            ms.builder.config.return_value.getOrCreate.return_value = mock_session
            build_spark_session(cfg)
        mock_session.sparkContext.setLogLevel.assert_called_once()
