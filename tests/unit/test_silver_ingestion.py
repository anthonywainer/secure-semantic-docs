"""Unit tests for silver ingestion text processing and pipeline logic."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from secure_semantic_docs.processing import (
    chunk_text,
    chunk_word_spans,
    normalise_whitespace,
    remove_control_characters,
    clean_text,
    chunk_document
)
from secure_semantic_docs.processing.chunk_builder import create_enriched_chunks


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


class TestChunkWordSpans:
    def test_empty_returns_empty(self):
        assert chunk_word_spans("") == []

    def test_short_text_returns_single_span(self):
        assert chunk_word_spans("hello world", chunk_size=400) == [(0, 2)]

    def test_overlap_matches_chunk_text_boundaries(self):
        source_document_text = " ".join(f"w{i}" for i in range(10))
        spans = chunk_word_spans(source_document_text, chunk_size=4, chunk_overlap=2)
        words = source_document_text.split()
        reconstructed = [" ".join(words[start:end]) for start, end in spans]
        assert reconstructed == chunk_text(source_document_text, chunk_size=4, chunk_overlap=2)

    def test_invalid_chunk_size_raises(self):
        with pytest.raises(ValueError, match="chunk_size"):
            chunk_word_spans("hello", chunk_size=0)

    def test_invalid_chunk_overlap_raises(self):
        with pytest.raises(ValueError, match="chunk_overlap"):
            chunk_word_spans("hello", chunk_size=4, chunk_overlap=4)


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
    def _document_row(**overrides):
        document_row = {
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
        document_row.update(overrides)
        return document_row

    def test_empty_text_returns_no_chunks(self):
        assert chunk_document(self._document_row(raw_text=""), 400, 80) == []

    def test_none_text_returns_no_chunks(self):
        assert chunk_document(self._document_row(raw_text=None), 400, 80) == []

    def test_returns_correct_chunk_keys(self):
        chunk_payloads = chunk_document(self._document_row(), 400, 80)
        assert len(chunk_payloads) == 1
        chunk_keys = set(chunk_payloads[0].keys())
        assert {"chunk_id", "document_id", "chunk_index", "chunk_text",
                "chunk_span", "classification", "allowed_roles", "owner", "department",
                "version", "source_path", "document_hash"} <= chunk_keys

    def test_chunk_index_is_sequential(self):
        document_row = self._document_row(
            raw_text=" ".join(f"w{i}" for i in range(20))
        )
        chunk_payloads = chunk_document(document_row, 4, 1)
        chunk_indexes = [p["chunk_index"] for p in chunk_payloads]
        assert chunk_indexes == list(range(len(chunk_payloads)))

    def test_missing_optional_fields_use_defaults(self):
        document_row = {"document_id": "x", "raw_text": "hello world"}
        chunk_payloads = chunk_document(document_row, 400, 80)
        assert chunk_payloads[0]["classification"] == "public"
        assert chunk_payloads[0]["owner"] == ""

    def test_string_allowed_roles_wrapped_in_list(self):
        document_row = {
            "document_id": "x",
            "raw_text": "hello world",
            "allowed_roles": "admin"
        }
        chunk_payloads = chunk_document(document_row, 400, 80)
        assert chunk_payloads[0]["allowed_roles"] == ["admin"]

    def test_non_iterable_allowed_roles_defaults_to_empty_list(self):
        chunk_payloads = chunk_document(
            self._document_row(raw_text="hello world", allowed_roles=123),
            400,
            80
        )
        assert chunk_payloads[0]["allowed_roles"] == []

    def test_chunk_span_tracks_word_indices(self):
        chunk_payloads = chunk_document(self._document_row(raw_text="one two three four"), 2, 0)
        assert chunk_payloads[0]["chunk_span"] == (0, 2)
        assert chunk_payloads[1]["chunk_span"] == (2, 4)


class TestBuildChunkDataframe:
    """Bronze rows no longer carry raw_text; tests use tmp_path with real files."""

    @staticmethod
    def _setup_raw_docs(tmp_path, files: dict[str, str]):
        """Create raw_documents dir under tmp_path and write given filename→content pairs."""
        raw_docs_dir = tmp_path / "synthetic_data" / "raw_documents"
        raw_docs_dir.mkdir(parents=True)
        for filename, text in files.items():
            (raw_docs_dir / filename).write_text(text, encoding="utf-8")
        return raw_docs_dir

    @staticmethod
    def _make_documents_df(spark, source_path: str = "d1.txt"):
        from pyspark.sql.types import ArrayType, StringType, StructField, StructType
        schema = StructType([
            StructField("document_id", StringType()),
            StructField("classification", StringType()),
            StructField("allowed_roles", ArrayType(StringType())),
            StructField("owner", StringType()),
            StructField("department", StringType()),
            StructField("version", StringType()),
            StructField("source_path", StringType()),
            StructField("document_hash", StringType())
        ])
        return spark.createDataFrame(
            [("d1", "internal", ["admin"], "bob", "ops", "2", source_path, "hash1")],
            schema=schema
        )

    def test_produces_dataframe_with_chunk_schema(self, spark, tmp_path):
        self._setup_raw_docs(tmp_path, {"d1.txt": "word " * 20})
        from secure_semantic_docs.models import Config
        config = Config(project_root=tmp_path)
        chunks_df = create_enriched_chunks(spark, self._make_documents_df(spark), config)
        field_names = {f.name for f in chunks_df.schema}
        assert {"chunk_id", "document_id", "chunk_span", "chunk_index"} <= field_names

    def test_uses_config_chunk_size(self, spark, tmp_path):
        from secure_semantic_docs.models import Config, ChunkingConfig
        self._setup_raw_docs(tmp_path, {"d1.txt": " ".join(f"w{i}" for i in range(30))})
        config = Config(
            project_root=tmp_path,
            chunking=ChunkingConfig(chunk_size=5, chunk_overlap=1)
        )
        chunks_df = create_enriched_chunks(spark, self._make_documents_df(spark), config)
        assert chunks_df.count() > 1

    def test_no_config_uses_defaults(self, spark, tmp_path):
        self._setup_raw_docs(tmp_path, {"d1.txt": "hello world"})
        from secure_semantic_docs.models import Config
        config = Config(project_root=tmp_path)
        chunks_df = create_enriched_chunks(spark, self._make_documents_df(spark), config)
        assert chunks_df.count() == 1

    def test_missing_file_produces_no_chunks(self, spark, tmp_path):
        self._setup_raw_docs(tmp_path, {})
        from secure_semantic_docs.models import Config
        config = Config(project_root=tmp_path)
        chunks_df = create_enriched_chunks(
            spark,
            self._make_documents_df(spark, source_path="missing.txt"),
            config
        )
        assert chunks_df.count() == 0

    def test_create_chunk_workset_builds_dataframe_from_partition_rdd(self, tmp_path):
        from secure_semantic_docs.models import Config, ReaderEntry, ReadersConfig
        from secure_semantic_docs.processing.chunk_builder import create_chunk_workset

        mock_spark = MagicMock()
        mock_documents_df = MagicMock()
        mock_rdd = MagicMock()
        mock_schema = MagicMock()
        mock_documents_df.rdd.mapPartitions.side_effect = (
            lambda func: (list(func(iter([]))), mock_rdd)[1]
        )
        config = Config(
            project_root=tmp_path,
            readers=ReadersConfig(entries={
                "raw_documents": ReaderEntry(options={"path": "/raw/docs"})
            })
        )

        with patch(
                "secure_semantic_docs.processing.chunk_builder._workset_schema",
                return_value=mock_schema
        ):
            result = create_chunk_workset(mock_spark, mock_documents_df, config)

        mock_documents_df.rdd.mapPartitions.assert_called_once()
        mock_spark.createDataFrame.assert_called_once_with(mock_rdd, schema=mock_schema)
        assert result is mock_spark.createDataFrame.return_value

    def test_create_chunk_workset_uses_default_raw_documents_dir(self, tmp_path):
        from secure_semantic_docs.models import Config
        from secure_semantic_docs.processing.chunk_builder import create_chunk_workset

        mock_spark = MagicMock()
        mock_documents_df = MagicMock()
        mock_rdd = MagicMock()
        mock_documents_df.rdd.mapPartitions.return_value = mock_rdd

        with patch("secure_semantic_docs.processing.chunk_builder._workset_schema"):
            create_chunk_workset(
                mock_spark,
                mock_documents_df,
                Config(project_root=tmp_path)
            )

        mock_documents_df.rdd.mapPartitions.assert_called_once()

    def test_create_enriched_chunks_selects_persisted_columns(self):
        from secure_semantic_docs.processing.chunk_builder import create_enriched_chunks

        mock_spark = MagicMock()
        mock_documents_df = MagicMock()
        mock_workset_df = MagicMock()
        mock_persisted_df = MagicMock()

        with (
            patch(
                "secure_semantic_docs.processing.chunk_builder.create_chunk_workset",
                return_value=mock_workset_df
            ) as mock_create,
            patch(
                "secure_semantic_docs.processing.chunk_builder.select_persisted_chunk_columns",
                return_value=mock_persisted_df
            ) as mock_select
        ):
            result = create_enriched_chunks(mock_spark, mock_documents_df, None)

        mock_create.assert_called_once_with(mock_spark, mock_documents_df, None)
        mock_select.assert_called_once_with(mock_workset_df)
        assert result is mock_persisted_df

    def test_select_persisted_chunk_columns_uses_schema_fields(self):
        from pyspark.sql.types import StringType, StructField, StructType
        from secure_semantic_docs.processing.chunk_builder import select_persisted_chunk_columns

        mock_chunks_df = MagicMock()
        schema = StructType([
            StructField("chunk_id", StringType()),
            StructField("document_id", StringType())
        ])

        with patch(
                "secure_semantic_docs.processing.chunk_builder.load_schema",
                return_value=schema
        ):
            result = select_persisted_chunk_columns(mock_chunks_df)

        mock_chunks_df.select.assert_called_once_with("chunk_id", "document_id")
        assert result is mock_chunks_df.select.return_value

    def test_workset_schema_adds_transient_chunk_text(self):
        from pyspark.sql.types import StringType, StructField, StructType
        from secure_semantic_docs.processing.chunk_builder import _workset_schema

        schema = StructType([StructField("chunk_id", StringType())])
        with patch(
                "secure_semantic_docs.processing.chunk_builder.load_schema",
                return_value=schema
        ):
            result = _workset_schema()

        assert "chunk_text" in result.fieldNames()


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


class TestReadDocumentText:
    """Direct unit tests for _read_document_text without Spark."""

    def test_returns_file_content(self, tmp_path):
        from secure_semantic_docs.processing.chunk_builder import _read_document_text
        (tmp_path / "doc.txt").write_text("hello world", encoding="utf-8")
        assert _read_document_text("some/path/doc.txt", str(tmp_path)) == "hello world"

    def test_searches_subdirectories(self, tmp_path):
        from secure_semantic_docs.processing.chunk_builder import _read_document_text
        subdir = tmp_path / "internal"
        subdir.mkdir()
        (subdir / "doc.txt").write_text("nested content", encoding="utf-8")
        assert _read_document_text("doc.txt", str(tmp_path)) == "nested content"

    def test_missing_file_returns_empty_string(self, tmp_path):
        from secure_semantic_docs.processing.chunk_builder import _read_document_text
        result = _read_document_text("missing.txt", str(tmp_path))
        assert result == ""

    def test_oserror_on_read_returns_empty_string(self, tmp_path, monkeypatch):
        from secure_semantic_docs.processing.chunk_builder import _read_document_text
        (tmp_path / "doc.txt").write_text("content", encoding="utf-8")
        monkeypatch.setattr("pathlib.Path.read_text", lambda *a, **kw: (_ for _ in ()).throw(OSError("permission denied")))
        result = _read_document_text("doc.txt", str(tmp_path))
        assert result == ""


class TestReadDocumentWords:
    def test_returns_cleaned_words(self, tmp_path):
        from secure_semantic_docs.processing.document_reader import read_document_words
        (tmp_path / "doc.txt").write_text("hello\x00  \nworld", encoding="utf-8")
        assert read_document_words("doc.txt", str(tmp_path)) == ["hello", "world"]


class TestEnrichPartition:
    """Direct unit tests for _enrich_partition without Spark."""

    def test_yields_enriched_rows_for_valid_document(self, tmp_path):
        from pyspark.sql import Row
        from secure_semantic_docs.processing.chunk_builder import _enrich_partition
        (tmp_path / "doc.txt").write_text("word " * 20, encoding="utf-8")
        rows = [Row(
            document_id="d1",
            source_path="doc.txt",
            classification="internal",
            allowed_roles=["admin"],
            owner="alice",
            department="eng",
            version="1",
            document_hash="abc123"
        )]
        results = list(_enrich_partition(iter(rows), 400, 80, str(tmp_path)))
        chunk_span = results[0][3]
        assert len(results) >= 1
        assert results[0][1] == "d1"
        assert isinstance(chunk_span, Row)
        assert chunk_span.start == 0
        assert chunk_span.end == 20

    def test_yields_nothing_for_missing_file(self, tmp_path):
        from pyspark.sql import Row
        from secure_semantic_docs.processing.chunk_builder import _enrich_partition
        rows = [Row(
            document_id="d1",
            source_path="missing.txt",
            classification="public",
            allowed_roles=[],
            owner="",
            department="",
            version="1",
            document_hash=""
        )]
        results = list(_enrich_partition(iter(rows), 400, 80, str(tmp_path)))
        assert results == []

    def test_invalid_chunk_span_raises_meaningful_error(self):
        from secure_semantic_docs.processing.chunk_builder import _chunk_span

        with pytest.raises(ValueError, match="chunk_span must be a two-item tuple"):
            _chunk_span(None)
