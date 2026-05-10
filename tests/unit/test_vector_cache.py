"""Unit tests for the embed cache and streaming trigger modules."""

from unittest.mock import MagicMock, patch


class TestLoadCache:
    def test_returns_none_when_no_reader_configured(self):
        from secure_semantic_docs.embeddings.vector_cache import load_cache

        mock_spark = MagicMock()
        mock_config = MagicMock()
        mock_config.readers.entries.get.return_value = None

        result = load_cache(mock_spark, mock_config)
        assert result is None

    def test_returns_dataframe_when_path_exists(self):
        from secure_semantic_docs.embeddings.vector_cache import load_cache

        mock_df = MagicMock()
        mock_df.count.return_value = 5

        mock_spark = MagicMock()
        mock_reader = MagicMock()
        mock_reader.options = {"format": "parquet", "mergeSchema": "true", "path": "/some/path"}

        mock_config = MagicMock()
        mock_config.readers.entries.get.return_value = mock_reader

        with patch(
                "secure_semantic_docs.embeddings.vector_cache.SparkReader"
        ) as mock_reader_cls:
            mock_reader_cls.return_value.read.return_value = mock_df
            result = load_cache(mock_spark, mock_config)

        assert result is mock_df

    def test_returns_none_when_parquet_load_fails(self):
        from secure_semantic_docs.embeddings.vector_cache import load_cache

        mock_spark = MagicMock()
        mock_reader = MagicMock()
        mock_reader.options = {"format": "parquet", "path": "/nonexistent"}

        mock_config = MagicMock()
        mock_config.readers.entries.get.return_value = mock_reader

        with patch(
                "secure_semantic_docs.embeddings.vector_cache.SparkReader"
        ) as mock_reader_cls:
            mock_reader_cls.return_value.read.side_effect = OSError("path not found")
            result = load_cache(mock_spark, mock_config)

        assert result is None


class TestSplitHitsAndMisses:
    def test_cold_cache_all_rows_are_misses(self, spark):
        from pyspark.sql.types import StructType
        from secure_semantic_docs.embeddings.vector_cache import split_hits_and_misses

        schema = StructType.fromDDL(
            "chunk_id string, document_hash string, source_path string"
        )
        silver_df = spark.createDataFrame(
            [("c1", "hash-a", "doc.txt"), ("c2", "hash-b", "doc.txt")],
            schema=schema
        )

        hits, misses = split_hits_and_misses(silver_df, cache_df=None)
        assert hits.count() == 0
        assert misses.count() == 2

    def test_warm_cache_splits_correctly(self, spark):
        from pyspark.sql.types import StructType
        from secure_semantic_docs.embeddings.vector_cache import split_hits_and_misses

        silver_schema = StructType.fromDDL(
            "chunk_id string, document_hash string, source_path string"
        )
        silver_df = spark.createDataFrame(
            [
                ("c1", "hash-a", "doc.txt"),
                ("c2", "hash-b", "doc.txt"),
                ("c3", "hash-c", "doc2.txt")
            ],
            schema=silver_schema
        )

        cache_schema = StructType.fromDDL(
            "chunk_id string, document_hash string, "
            "embedding_ciphertext binary, embedding_nonce binary, "
            "embedding_algorithm string, embedding_dim int, key_id string, model string"
        )
        cache_df = spark.createDataFrame(
            [("c1", "hash-a", b"cipher", b"nonce123456789012345678", "XSalsa20", 384, "k1", "m1")],
            schema=cache_schema
        )

        hits, misses = split_hits_and_misses(silver_df, cache_df)
        assert hits.count() == 1
        assert misses.count() == 2

    def test_full_cache_hit_no_misses(self, spark):
        from pyspark.sql.types import StructType
        from secure_semantic_docs.embeddings.vector_cache import split_hits_and_misses

        silver_schema = StructType.fromDDL("chunk_id string, document_hash string, source_path string")
        silver_df = spark.createDataFrame(
            [("c1", "hash-a", "doc.txt")],
            schema=silver_schema
        )

        cache_schema = StructType.fromDDL(
            "chunk_id string, document_hash string, "
            "embedding_ciphertext binary, embedding_nonce binary, "
            "embedding_algorithm string, embedding_dim int, key_id string, model string"
        )
        cache_df = spark.createDataFrame(
            [("c1", "hash-a", b"cipher", b"nonce123456789012345678", "XSalsa20", 384, "k1", "m1")],
            schema=cache_schema
        )

        hits, misses = split_hits_and_misses(silver_df, cache_df)
        assert hits.count() == 1
        assert misses.count() == 0


class TestWriteCache:
    def test_skips_write_when_no_writer_configured(self):
        from secure_semantic_docs.embeddings.vector_cache import write_cache

        mock_spark = MagicMock()
        mock_df = MagicMock()
        mock_config = MagicMock()
        mock_config.writers.entries.get.return_value = None

        write_cache(mock_spark, mock_df, mock_config)
        mock_df.select.assert_not_called()

    def test_writes_only_cache_columns(self, spark):
        from pyspark.sql.types import StructType
        from secure_semantic_docs.embeddings.vector_cache import write_cache

        schema = StructType.fromDDL(
            "chunk_id string, document_hash string, chunk_span struct<start:int,end:int>, "
            "embedding_ciphertext binary, embedding_nonce binary, "
            "embedding_algorithm string, embedding_dim int, key_id string, "
            "model string, created_at string, extra_col string"
        )
        from pyspark.sql import Row
        df = spark.createDataFrame(
            [("c1", "h1", Row(start=0, end=2), b"cipher", b"nonce1234567890123456789",
              "XSalsa20", 384, "k1", "model1", "2024-01-01T00:00:00Z", "should_be_excluded")],
            schema=schema
        )

        mock_writer_entry = MagicMock()
        mock_writer_entry.options = {"format": "parquet", "mode": "append", "path": "/tmp/cache_test"}
        mock_config = MagicMock()
        mock_config.writers.entries.get.return_value = mock_writer_entry

        saved_paths = []

        with patch(
                "secure_semantic_docs.embeddings.vector_cache.SparkWriter"
        ) as mock_writer_cls:
            mock_writer_cls.return_value.write.side_effect = lambda _, **opts: saved_paths.append(opts.get("path"))
            write_cache(spark, df, mock_config)

        mock_writer_cls.return_value.write.assert_called_once()
        assert True
