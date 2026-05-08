"""Unit tests for silver ingestion text processing and pipeline logic."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from secure_semantic_docs.processing import (
    chunk_text,
    normalise_whitespace,
    remove_control_characters,
    clean_text,
    chunk_document
)
from secure_semantic_docs.silver_ingestion import process_bronze_to_silver


class TestChunkText:
    def test_empty_returns_empty(self):
        assert chunk_text("") == []

    def test_whitespace_only_returns_empty(self):
        assert chunk_text("   ") == []

    def test_short_text_returns_single_chunk(self):
        text_chunks = chunk_text("hello world", chunk_size=400)
        assert text_chunks == ["hello world"]

    def test_splits_into_multiple_chunks(self):
        source_document_text = " ".join(f"word{i}" for i in range(10))
        text_chunks = chunk_text(source_document_text, chunk_size=4, chunk_overlap=1)
        assert len(text_chunks) > 1

    def test_overlap_shares_words(self):
        source_document_text = " ".join(f"w{i}" for i in range(10))
        text_chunks = chunk_text(source_document_text, chunk_size=4, chunk_overlap=2)
        first_chunk_overlap_words = text_chunks[0].split()[-2:]
        second_chunk_overlap_words = text_chunks[1].split()[:2]
        assert first_chunk_overlap_words == second_chunk_overlap_words

    def test_last_chunk_does_not_overflow(self):
        source_document_text = " ".join(f"w{i}" for i in range(7))
        text_chunks = chunk_text(source_document_text, chunk_size=4, chunk_overlap=1)
        chunked_word_count = sum(len(text_chunk.split()) for text_chunk in text_chunks)
        assert chunked_word_count >= 7

    def test_invalid_chunk_size_raises(self):
        with pytest.raises(ValueError, match="chunk_size"):
            chunk_text("hello", chunk_size=0)

    def test_negative_chunk_overlap_raises(self):
        with pytest.raises(ValueError, match="chunk_overlap"):
            chunk_text("hello", chunk_size=4, chunk_overlap=-1)

    def test_chunk_overlap_equals_size_raises(self):
        with pytest.raises(ValueError, match="chunk_overlap"):
            chunk_text("hello", chunk_size=4, chunk_overlap=4)


class TestNormaliseWhitespace:
    def test_strips_trailing_spaces_before_newline(self):
        assert "\n" in normalise_whitespace("hello  \nworld")

    def test_collapses_multiple_blank_lines(self):
        normalised_text = normalise_whitespace("a\n\n\n\nb")
        assert "\n\n\n" not in normalised_text

    def test_strips_surrounding_whitespace(self):
        assert normalise_whitespace("  hello  ") == "hello"


class TestRemoveControlCharacters:
    def test_removes_null_byte(self):
        assert "\x00" not in remove_control_characters("hello\x00world")

    def test_preserves_tab_and_newline(self):
        source_text = "hello\tworld\nline2"
        assert remove_control_characters(source_text) == source_text

    def test_preserves_unicode(self):
        source_text = "café résumé"
        assert remove_control_characters(source_text) == source_text


class TestCleanText:
    def test_composition_removes_control_and_normalises(self):
        cleaned_text = clean_text("hello\x00  \nworld\n\n\n\n!")
        assert "\x00" not in cleaned_text
        assert "\n\n\n" not in cleaned_text


class TestChunkDocument:
    @staticmethod
    def _bronze_document_row(**overrides):
        bronze_document_row = {
            "document_id": "doc-1",
            "raw_text": "word " * 10,
            "classification": "public",
            "allowed_roles": ["reader"],
            "owner": "alice",
            "department": "eng",
            "version": "1",
            "source_path": "/path/to/doc",
            "document_hash": "abc123"
        }
        bronze_document_row.update(overrides)
        return bronze_document_row

    def test_empty_text_returns_no_chunks(self):
        assert chunk_document(self._bronze_document_row(raw_text=""), 400, 80) == []

    def test_none_text_returns_no_chunks(self):
        assert chunk_document(self._bronze_document_row(raw_text=None), 400, 80) == []

    def test_returns_correct_chunk_keys(self):
        silver_chunk_payloads = chunk_document(self._bronze_document_row(), 400, 80)
        assert len(silver_chunk_payloads) == 1
        silver_chunk_keys = set(silver_chunk_payloads[0].keys())
        assert {"chunk_id", "document_id", "chunk_index", "chunk_text",
                "classification", "allowed_roles", "owner", "department",
                "version", "source_path", "document_hash"} <= silver_chunk_keys

    def test_chunk_index_is_sequential(self):
        bronze_document_row = self._bronze_document_row(
            raw_text=" ".join(f"w{i}" for i in range(20))
        )
        silver_chunk_payloads = chunk_document(bronze_document_row, 4, 1)
        chunk_indexes = [
            silver_chunk_payload["chunk_index"]
            for silver_chunk_payload in silver_chunk_payloads
        ]
        assert chunk_indexes == list(range(len(silver_chunk_payloads)))

    def test_missing_optional_fields_use_defaults(self):
        bronze_document_row = {"document_id": "x", "raw_text": "hello world"}
        silver_chunk_payloads = chunk_document(bronze_document_row, 400, 80)
        assert silver_chunk_payloads[0]["classification"] == "public"
        assert silver_chunk_payloads[0]["owner"] == ""

    def test_string_allowed_roles_wrapped_in_list(self):
        bronze_document_row = {
            "document_id": "x",
            "raw_text": "hello world",
            "allowed_roles": "admin"
        }
        silver_chunk_payloads = chunk_document(bronze_document_row, 400, 80)
        assert silver_chunk_payloads[0]["allowed_roles"] == ["admin"]


class TestProcessBronzeToSilver:
    def test_produces_dataframe_with_silver_schema(self, spark):
        from pyspark.sql import Row
        bronze_document_rows = [Row(
            document_id="d1",
            raw_text="word " * 20,
            classification="internal",
            allowed_roles=["admin"],
            owner="bob",
            department="ops",
            version="2",
            source_path="/docs/d1.txt",
            document_hash="hash1"
        )]
        bronze_documents_df = spark.createDataFrame(bronze_document_rows)
        silver_chunks_df = process_bronze_to_silver(spark, bronze_documents_df)
        silver_field_names = {schema_field.name for schema_field in silver_chunks_df.schema}
        assert {"chunk_id", "document_id", "chunk_text", "chunk_index"} <= silver_field_names

    def test_uses_config_chunk_size(self, spark):
        from pyspark.sql.types import ArrayType, StringType, StructField, StructType
        from secure_semantic_docs.models import Config, ChunkingConfig
        bronze_documents_schema = StructType([
            StructField("document_id", StringType()),
            StructField("raw_text", StringType()),
            StructField("classification", StringType()),
            StructField("allowed_roles", ArrayType(StringType())),
            StructField("owner", StringType()),
            StructField("department", StringType()),
            StructField("version", StringType()),
            StructField("source_path", StringType()),
            StructField("document_hash", StringType())
        ])
        bronze_document_records = [
            (
                "d1",
                " ".join(f"w{i}" for i in range(30)),
                "public",
                [],
                "x",
                "y",
                "1",
                "/p",
                "h"
            )
        ]
        bronze_documents_df = spark.createDataFrame(
            bronze_document_records, schema=bronze_documents_schema
        )
        pipeline_config = Config(chunking=ChunkingConfig(chunk_size=5, chunk_overlap=1))
        silver_chunks_df = process_bronze_to_silver(
            spark, bronze_documents_df, config=pipeline_config
        )
        assert silver_chunks_df.count() > 1

    def test_no_config_uses_defaults(self, spark):
        from pyspark.sql.types import ArrayType, StringType, StructField, StructType
        bronze_documents_schema = StructType([
            StructField("document_id", StringType()),
            StructField("raw_text", StringType()),
            StructField("classification", StringType()),
            StructField("allowed_roles", ArrayType(StringType())),
            StructField("owner", StringType()),
            StructField("department", StringType()),
            StructField("version", StringType()),
            StructField("source_path", StringType()),
            StructField("document_hash", StringType())
        ])
        bronze_document_records = [("d1", "hello world", "public", [], "", "", "", "", "")]
        bronze_documents_df = spark.createDataFrame(
            bronze_document_records, schema=bronze_documents_schema
        )
        silver_chunks_df = process_bronze_to_silver(spark, bronze_documents_df, config=None)
        assert silver_chunks_df.count() == 1


class TestSilverMain:
    def test_main_calls_ingest_with_spark_and_config(self):
        mock_pipeline_config = MagicMock()
        mock_spark_session = MagicMock()

        with (
            patch("secure_semantic_docs.silver_ingestion.configure_logging"),
            patch(
                "secure_semantic_docs.silver_ingestion.load_config",
                return_value=mock_pipeline_config
            ),
            patch(
                "secure_semantic_docs.silver_ingestion.build_spark_session",
                return_value=mock_spark_session
            ) as mock_build_spark_session,
            patch("secure_semantic_docs.silver_ingestion.ingest") as mock_ingest
        ):
            from secure_semantic_docs.silver_ingestion import main
            main()

        mock_build_spark_session.assert_called_once_with(mock_pipeline_config)
        mock_ingest.assert_called_once_with(mock_spark_session, mock_pipeline_config)

    def test_main_suppresses_py4j_logs(self):
        with (
            patch("secure_semantic_docs.silver_ingestion.configure_logging"),
            patch(
                "secure_semantic_docs.silver_ingestion.load_config",
                return_value=MagicMock()
            ),
            patch(
                "secure_semantic_docs.silver_ingestion.build_spark_session",
                return_value=MagicMock()
            ),
            patch("secure_semantic_docs.silver_ingestion.ingest")
        ):
            from secure_semantic_docs.silver_ingestion import main
            main()

        assert logging.getLogger("py4j").level == logging.ERROR
