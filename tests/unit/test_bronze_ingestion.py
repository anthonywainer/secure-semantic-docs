"""Unit tests for the bronze ingestion pipeline entry point."""

import logging
from unittest.mock import MagicMock, patch


class TestMain:
    def test_main_calls_ingest_with_spark_and_config(self):
        mock_cfg = MagicMock()
        mock_spark = MagicMock()

        with (
            patch("secure_semantic_docs.bronze_ingestion.configure_logging"),
            patch("secure_semantic_docs.bronze_ingestion.load_config", return_value=mock_cfg),
            patch("secure_semantic_docs.bronze_ingestion.build_spark_session", return_value=mock_spark) as mock_bs,
            patch("secure_semantic_docs.bronze_ingestion.ingest") as mock_ingest
        ):
            from secure_semantic_docs.bronze_ingestion import main
            main()

        mock_bs.assert_called_once_with(mock_cfg)
        mock_ingest.assert_called_once_with(mock_spark, mock_cfg)

    def test_main_suppresses_py4j_logs(self):
        with (
            patch("secure_semantic_docs.bronze_ingestion.configure_logging"),
            patch("secure_semantic_docs.bronze_ingestion.load_config", return_value=MagicMock()),
            patch("secure_semantic_docs.bronze_ingestion.build_spark_session", return_value=MagicMock()),
            patch("secure_semantic_docs.bronze_ingestion.ingest")
        ):
            from secure_semantic_docs.bronze_ingestion import main
            main()

        assert logging.getLogger("py4j").level == logging.ERROR
