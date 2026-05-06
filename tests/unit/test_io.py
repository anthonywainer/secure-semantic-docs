"""Unit tests for SparkReader and SparkWriter."""

from unittest.mock import MagicMock

import pytest

from secure_semantic_docs.io import SparkReader, SparkWriter


class TestSparkReaderRead:
    def setup_method(self):
        self.spark = MagicMock()
        self.reader = SparkReader(self.spark)

    def test_read_dispatches_to_load_when_path_given(self):
        self.reader.load = MagicMock()
        self.reader.read(path="/synthetic_data/bronze", format="parquet")
        self.reader.load.assert_called_once_with("/synthetic_data/bronze", False, format="parquet")

    def test_read_dispatches_to_table_when_table_name_given(self):
        self.reader.table = MagicMock()
        self.reader.read(table_name="catalog.bronze.docs")
        self.reader.table.assert_called_once_with("catalog.bronze.docs", False)

    def test_read_raises_when_both_table_and_path_given(self):
        with pytest.raises(ValueError, match="not both"):
            self.reader.read(table_name="t", path="/p")

    def test_read_extracts_path_from_options_dict(self):
        self.reader.load = MagicMock()
        self.reader.read(options={"path": "/from/options", "format": "csv"})
        self.reader.load.assert_called_once_with("/from/options", False, format="csv")

    def test_read_raises_when_options_not_dict(self):
        with pytest.raises(TypeError, match="must be a dict"):
            self.reader.read(options="bad")

    def test_read_stream_flag_forwarded(self):
        self.reader.load = MagicMock()
        self.reader.read(path="/p", stream=True, format="parquet")
        self.reader.load.assert_called_once_with("/p", True, format="parquet")

    def test_load_uses_read_stream_when_stream_true(self):
        mock_stream_reader = MagicMock()
        self.spark.readStream = mock_stream_reader
        self.reader.load("/p", stream=True, format="parquet")
        mock_stream_reader.load.assert_called_once_with("/p", format="parquet")

    def test_load_uses_read_when_stream_false(self):
        mock_reader = MagicMock()
        self.spark.read = mock_reader
        self.reader.load("/p", stream=False, format="parquet")
        mock_reader.load.assert_called_once_with("/p", format="parquet")

    def test_table_uses_read_stream_when_stream_true(self):
        self.spark.readStream = MagicMock()
        self.reader.table("my_table", stream=True)
        self.spark.readStream.table.assert_called_once_with("my_table")

    def test_table_uses_read_when_stream_false(self):
        self.spark.read = MagicMock()
        self.reader.table("my_table", stream=False)
        self.spark.read.table.assert_called_once_with("my_table")


class TestSparkWriterWrite:
    def setup_method(self):
        self.spark = MagicMock()
        self.writer = SparkWriter(self.spark)

    def test_write_dispatches_to_save_when_path_given(self):
        df = MagicMock()
        self.writer.save = MagicMock()
        self.writer.write(df, path="/out", format="parquet")
        self.writer.save.assert_called_once_with(df, "/out", stream=False, format="parquet")

    def test_write_dispatches_to_save_table_when_table_given(self):
        df = MagicMock()
        self.writer.save_table = MagicMock()
        self.writer.write(df, table_name="catalog.t", format="parquet")
        self.writer.save_table.assert_called_once_with(
            df, "catalog.t", stream=False, format="parquet"
        )

    def test_write_raises_when_both_table_and_path_given(self):
        df = MagicMock()
        with pytest.raises(ValueError, match="not both"):
            self.writer.write(df, table_name="t", path="/p")

    def test_write_extracts_path_from_options_dict(self):
        df = MagicMock()
        self.writer.save = MagicMock()
        self.writer.write(df, options={"path": "/from/options", "format": "parquet"})
        self.writer.save.assert_called_once_with(
            df, "/from/options", stream=False, format="parquet"
        )

    def test_write_raises_when_options_not_dict(self):
        df = MagicMock()
        with pytest.raises(TypeError, match="must be a dict"):
            self.writer.write(df, options="bad")

    def test_save_batch_applies_format_and_mode(self):
        df = MagicMock()
        mock_write = MagicMock()
        df.write = mock_write
        self.writer.save(df, "/out", stream=False, format="parquet", mode="overwrite")
        mock_write.format.assert_called_once_with("parquet")
        mock_write.format.return_value.mode.assert_called_once_with("overwrite")

    def test_save_stream_uses_write_stream(self):
        df = MagicMock()
        mock_write_stream = MagicMock()
        df.writeStream = mock_write_stream
        self.writer.save(df, "/out", stream=True, format="parquet")
        mock_write_stream.format.assert_called_once_with("parquet")

    def test_save_table_batch_calls_save_as_table(self):
        df = MagicMock()
        mock_write = MagicMock()
        df.write = mock_write
        self.writer.save_table(df, "my.table", stream=False, format="delta", mode="append")
        mock_write.format.assert_called_once_with("delta")
        (
            mock_write.format.return_value
            .mode.return_value
            .options.return_value
            .saveAsTable.assert_called_once_with("my.table")
        )

    def test_save_table_stream_calls_to_table(self):
        df = MagicMock()
        mock_write_stream = MagicMock()
        df.writeStream = mock_write_stream
        self.writer.save_table(df, "my.table", stream=True, format="delta")
        mock_write_stream.format.assert_called_once_with("delta")
        (
            mock_write_stream.format.return_value
            .outputMode.return_value
            .options.return_value
            .toTable.assert_called_once_with("my.table")
        )


class TestSparkReaderFromConfig:
    """Test SparkReader integration with ReaderEntry config objects."""

    def test_read_with_entry_options(self):
        from secure_semantic_docs.models.reader_models import ReaderEntry

        entry = ReaderEntry(stream=False, options={"format": "parquet", "mergeSchema": "true"})
        spark = MagicMock()
        reader = SparkReader(spark)
        reader.load = MagicMock()

        reader.read(path="/synthetic_data", stream=entry.stream, **entry.options)
        reader.load.assert_called_once_with(
            "/synthetic_data", False, format="parquet", mergeSchema="true"
        )


class TestSparkWriterFromConfig:
    """Test SparkWriter integration with WriterEntry config objects."""

    def test_write_with_entry_options(self):
        from secure_semantic_docs.models.writer_models import WriterEntry

        entry = WriterEntry(stream=False, options={"format": "parquet", "mode": "overwrite"})
        df = MagicMock()
        spark = MagicMock()
        writer = SparkWriter(spark)
        writer.save = MagicMock()

        writer.write(df, stream=entry.stream, path="/out", **entry.options)
        writer.save.assert_called_once_with(
            df, "/out", stream=False, format="parquet", mode="overwrite"
        )
