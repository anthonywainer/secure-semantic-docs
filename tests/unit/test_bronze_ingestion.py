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


class TestIngest:
    def test_ingest_reads_transforms_and_writes(self):
        """ingest() must call reader, conform, and writer with the right arguments."""
        mock_spark = MagicMock()
        mock_cfg = MagicMock()
        mock_raw_df = MagicMock()
        mock_documents_df = MagicMock()

        mock_cfg.readers = {"metadata_documents": MagicMock(options={"path": "/bronze"})}
        mock_cfg.writers = {"bronze_documents": MagicMock(options={"path": "/out"})}

        with (
            patch("secure_semantic_docs.bronze_ingestion.SparkReader") as mock_reader_cls,
            patch("secure_semantic_docs.bronze_ingestion.conform_document_metadata", return_value=mock_documents_df),
            patch("secure_semantic_docs.bronze_ingestion.SparkWriter") as mock_writer_cls
        ):
            mock_reader_cls.return_value.read.return_value = mock_raw_df

            from secure_semantic_docs.bronze_ingestion import ingest
            ingest(mock_spark, mock_cfg)

        mock_reader_cls.assert_called_once_with(mock_spark)
        mock_reader_cls.return_value.read.assert_called_once_with(path="/bronze")
        mock_writer_cls.assert_called_once_with(mock_spark)
        mock_writer_cls.return_value.write.assert_called_once_with(mock_documents_df, path="/out")

    def test_ingest_uses_load_config_when_cfg_is_none(self):
        """ingest() calls load_config() when cfg is not provided."""
        mock_spark = MagicMock()
        mock_cfg = MagicMock()
        mock_cfg.readers = {"metadata_documents": MagicMock(options={})}
        mock_cfg.writers = {"bronze_documents": MagicMock(options={})}

        with (
            patch("secure_semantic_docs.bronze_ingestion.load_config", return_value=mock_cfg) as mock_load,
            patch("secure_semantic_docs.bronze_ingestion.SparkReader"),
            patch("secure_semantic_docs.bronze_ingestion.conform_document_metadata", return_value=MagicMock()),
            patch("secure_semantic_docs.bronze_ingestion.SparkWriter")
        ):
            from secure_semantic_docs.bronze_ingestion import ingest
            ingest(mock_spark, None)

        mock_load.assert_called_once()
