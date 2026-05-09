"""Unit tests for the embeddings package and gold ingestion pipeline."""

import logging
import os
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from secure_semantic_docs.core.exceptions import EmbeddingError
from secure_semantic_docs.embeddings.model_loader import resolve_device
from secure_semantic_docs.embeddings.worker_env import configure_worker_environment, worker_safe_device


class TestConfigureWorkerEnvironment:
    def test_sets_tokenizers_parallelism(self, monkeypatch):
        import secure_semantic_docs.embeddings.worker_env as wenv
        monkeypatch.setattr(wenv, "_CONFIGURED", False)
        monkeypatch.delenv("TOKENIZERS_PARALLELISM", raising=False)
        configure_worker_environment()
        assert os.environ["TOKENIZERS_PARALLELISM"] == "false"

    def test_sets_omp_threads(self, monkeypatch):
        import secure_semantic_docs.embeddings.worker_env as wenv
        monkeypatch.setattr(wenv, "_CONFIGURED", False)
        monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
        configure_worker_environment()
        assert os.environ["OMP_NUM_THREADS"] == "1"

    def test_sets_mkl_threads(self, monkeypatch):
        import secure_semantic_docs.embeddings.worker_env as wenv
        monkeypatch.setattr(wenv, "_CONFIGURED", False)
        monkeypatch.delenv("MKL_NUM_THREADS", raising=False)
        configure_worker_environment()
        assert os.environ["MKL_NUM_THREADS"] == "1"

    def test_sets_loky_max_cpu_count(self, monkeypatch):
        import secure_semantic_docs.embeddings.worker_env as wenv
        monkeypatch.setattr(wenv, "_CONFIGURED", False)
        monkeypatch.delenv("LOKY_MAX_CPU_COUNT", raising=False)
        configure_worker_environment()
        assert os.environ["LOKY_MAX_CPU_COUNT"] == "1"

    def test_idempotent_second_call_does_not_overwrite(self, monkeypatch):
        import secure_semantic_docs.embeddings.worker_env as wenv
        monkeypatch.setattr(wenv, "_CONFIGURED", False)
        configure_worker_environment()
        os.environ["OMP_NUM_THREADS"] = "99"
        configure_worker_environment()
        assert os.environ["OMP_NUM_THREADS"] == "99"

    def test_sets_configured_flag(self, monkeypatch):
        import secure_semantic_docs.embeddings.worker_env as wenv
        monkeypatch.setattr(wenv, "_CONFIGURED", False)
        configure_worker_environment()
        assert wenv._CONFIGURED is True  # noqa: SLF001


class TestWorkerSafeDevice:
    def test_mps_overridden_to_cpu(self):
        assert worker_safe_device("mps") == "cpu"

    def test_cpu_unchanged(self):
        assert worker_safe_device("cpu") == "cpu"

    def test_cuda_unchanged(self):
        assert worker_safe_device("cuda") == "cuda"

    def test_cuda_index_unchanged(self):
        assert worker_safe_device("cuda:0") == "cuda:0"


class TestResolveEmbeddingPartitions:
    @staticmethod
    def _call(total_executor_cores: int, configured: int, is_local_mode: bool) -> int:
        from secure_semantic_docs.embeddings.chunk_embedder import _resolve_embedding_partitions  # noqa: PLC2701
        return _resolve_embedding_partitions(total_executor_cores, configured, is_local_mode)

    def test_local_mode_always_returns_one(self):
        assert self._call(total_executor_cores=16, configured=0, is_local_mode=True) == 1

    def test_local_mode_ignores_configured(self):
        assert self._call(total_executor_cores=8, configured=32, is_local_mode=True) == 1

    def test_cluster_configured_takes_precedence(self):
        assert self._call(total_executor_cores=8, configured=4, is_local_mode=False) == 4

    def test_cluster_falls_back_to_total_executor_cores(self):
        assert self._call(total_executor_cores=12, configured=0, is_local_mode=False) == 12

    def test_cluster_guards_against_zero_cores(self):
        assert self._call(total_executor_cores=0, configured=0, is_local_mode=False) == 1


class TestResolveDevice:
    def test_passthrough_cpu(self):
        assert resolve_device("cpu") == "cpu"

    def test_passthrough_cuda(self):
        assert resolve_device("cuda") == "cuda"

    def test_passthrough_mps(self):
        assert resolve_device("mps") == "mps"

    def test_passthrough_cuda_index(self):
        assert resolve_device("cuda:1") == "cuda:1"

    def test_auto_no_torch_falls_back_to_cpu(self):
        with patch.dict("sys.modules", {"torch": None}):
            assert resolve_device("auto") == "cpu"

    def test_auto_cuda_available(self):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert resolve_device("auto") == "cuda"

    def test_auto_mps_available(self):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = True
        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert resolve_device("auto") == "mps"

    def test_auto_neither_cuda_nor_mps_falls_back_to_cpu(self):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = False
        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert resolve_device("auto") == "cpu"


class TestLoadCachedModel:
    @staticmethod
    def _make_mock_model() -> MagicMock:
        return MagicMock(name="SentenceTransformer")

    def test_loads_model_and_returns_it(self, monkeypatch):
        import secure_semantic_docs.embeddings.model_loader as ml
        monkeypatch.setattr(ml, "_MODEL_CACHE", {})
        mock_model = self._make_mock_model()
        mock_cls = MagicMock(return_value=mock_model)
        with patch.dict("sys.modules", {"sentence_transformers": MagicMock(SentenceTransformer=mock_cls)}):
            from secure_semantic_docs.embeddings.model_loader import load_cached_model
            result = load_cached_model("all-MiniLM-L6-v2", "cpu")
        assert result is mock_model

    def test_second_call_reuses_cached_instance(self, monkeypatch):
        import secure_semantic_docs.embeddings.model_loader as ml
        monkeypatch.setattr(ml, "_MODEL_CACHE", {})
        mock_model = self._make_mock_model()
        mock_cls = MagicMock(return_value=mock_model)
        mock_st = MagicMock(SentenceTransformer=mock_cls)
        with patch.dict("sys.modules", {"sentence_transformers": mock_st}):
            from secure_semantic_docs.embeddings.model_loader import load_cached_model
            load_cached_model("all-MiniLM-L6-v2", "cpu")
            load_cached_model("all-MiniLM-L6-v2", "cpu")
        assert mock_cls.call_count == 1

    def test_different_device_creates_separate_entry(self, monkeypatch):
        import secure_semantic_docs.embeddings.model_loader as ml
        monkeypatch.setattr(ml, "_MODEL_CACHE", {})
        mock_cls = MagicMock(side_effect=lambda name, device: MagicMock(name=f"{name}@{device}"))
        mock_st = MagicMock(SentenceTransformer=mock_cls)
        with patch.dict("sys.modules", {"sentence_transformers": mock_st}):
            from secure_semantic_docs.embeddings.model_loader import load_cached_model
            m1 = load_cached_model("all-MiniLM-L6-v2", "cpu")
            m2 = load_cached_model("all-MiniLM-L6-v2", "cuda")
        assert m1 is not m2
        assert mock_cls.call_count == 2

    def test_logs_loading_info(self, monkeypatch, caplog):
        import secure_semantic_docs.embeddings.model_loader as ml
        monkeypatch.setattr(ml, "_MODEL_CACHE", {})
        mock_model_instance = MagicMock()
        mock_cls = MagicMock(return_value=mock_model_instance)
        with patch.dict("sys.modules", {"sentence_transformers": MagicMock(SentenceTransformer=mock_cls)}):
            from secure_semantic_docs.embeddings.model_loader import load_cached_model
            load_cached_model("all-MiniLM-L6-v2", "cpu")
        mock_cls.assert_called_once_with("all-MiniLM-L6-v2", device="cpu")


def _make_rows(*texts: str):
    """Build mock Spark Row objects for embed_partition tests."""

    def make_row(idx: int, text: str):
        row = MagicMock()
        row.asDict.return_value = {
            "chunk_id": f"c{idx}",
            "document_id": "doc-1",
            "chunk_text": text,
            "classification": "public",
            "allowed_roles": ["reader"],
            "owner": "alice",
            "department": "eng",
            "sensitivity_score": 0.1,
            "source_path": "/path",
            "version": "1",
            "document_hash": "abc"
        }
        return row

    return iter([make_row(i, t) for i, t in enumerate(texts)])


def _mock_model(dim: int = 4) -> MagicMock:
    """Stub SentenceTransformer whose encode() returns float32 arrays."""
    model = MagicMock()

    def encode(texts, **_kwargs):
        return np.zeros((len(texts), dim), dtype=np.float32)

    model.encode.side_effect = encode
    return model


class TestEmbedPartition:
    @staticmethod
    def _call(
            rows: Iterator,
            model_name: str = "m",
            device: str = "cpu",
            batch_size: int = 32,
            normalize: bool = True,
            created_at: str = "2024-01-01T00:00:00Z"
    ) -> list:
        from secure_semantic_docs.embeddings.chunk_embedder import embed_partition
        return list(embed_partition(rows, model_name, device, batch_size, normalize, created_at))

    @staticmethod
    def _patch_infra(mock_model):
        """Patch worker_env and model_loader so no real I/O happens."""
        return (
            patch("secure_semantic_docs.embeddings.chunk_embedder.configure_worker_environment"),
            patch(
                "secure_semantic_docs.embeddings.chunk_embedder.load_cached_model",
                return_value=mock_model
            )
        )

    def test_empty_partition_yields_nothing(self):
        with (
            patch("secure_semantic_docs.embeddings.chunk_embedder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.chunk_embedder.load_cached_model", return_value=_mock_model())
        ):
            result = self._call(iter([]))
        assert result == []

    def test_returns_one_tuple_per_row(self):
        mock_model = _mock_model(dim=4)
        with (
            patch("secure_semantic_docs.embeddings.chunk_embedder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.chunk_embedder.load_cached_model", return_value=mock_model)
        ):
            result = self._call(_make_rows("hello", "world"))
        assert len(result) == 2

    def test_tuple_has_correct_chunk_id(self):
        mock_model = _mock_model(dim=4)
        with (
            patch("secure_semantic_docs.embeddings.chunk_embedder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.chunk_embedder.load_cached_model", return_value=mock_model)
        ):
            result = self._call(_make_rows("hello"))
        assert result[0][0] == "c0"

    def test_tuple_has_embedding_list(self):
        mock_model = _mock_model(dim=4)
        with (
            patch("secure_semantic_docs.embeddings.chunk_embedder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.chunk_embedder.load_cached_model", return_value=mock_model)
        ):
            result = self._call(_make_rows("hello"))
        embedding = result[0][2]
        assert isinstance(embedding, list)
        assert len(embedding) == 4

    def test_model_name_stamped_on_row(self):
        mock_model = _mock_model(dim=4)
        with (
            patch("secure_semantic_docs.embeddings.chunk_embedder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.chunk_embedder.load_cached_model", return_value=mock_model)
        ):
            result = self._call(_make_rows("hello"), model_name="my-model")
        assert result[0][3] == "my-model"

    def test_created_at_stamped_on_row(self):
        mock_model = _mock_model(dim=4)
        ts = "2024-06-01T12:00:00Z"
        with (
            patch("secure_semantic_docs.embeddings.chunk_embedder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.chunk_embedder.load_cached_model", return_value=mock_model)
        ):
            result = self._call(_make_rows("hello"), created_at=ts)
        assert result[0][4] == ts

    def test_sensitivity_score_coerced_to_float(self):
        mock_model = _mock_model(dim=4)
        row = MagicMock()
        row.asDict.return_value = {
            "chunk_id": "c0",
            "document_id": "doc-1",
            "chunk_text": "text",
            "sensitivity_score": None
        }
        with (
            patch("secure_semantic_docs.embeddings.chunk_embedder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.chunk_embedder.load_cached_model", return_value=mock_model)
        ):
            result = self._call(iter([row]))
        assert isinstance(result[0][9], float)
        assert result[0][9] == 0.0

    def test_encode_failure_raises_embedding_error(self):
        failing_model = MagicMock()
        failing_model.encode.side_effect = RuntimeError("GPU OOM")
        with (
            patch("secure_semantic_docs.embeddings.chunk_embedder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.chunk_embedder.load_cached_model", return_value=failing_model)
        ):
            with pytest.raises(EmbeddingError, match="Batch encode failed"):
                self._call(_make_rows("hello"))

    def test_calls_encode_once_for_full_partition(self):
        mock_model = _mock_model(dim=4)
        with (
            patch("secure_semantic_docs.embeddings.chunk_embedder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.chunk_embedder.load_cached_model", return_value=mock_model)
        ):
            self._call(_make_rows("a", "b", "c"))
        assert mock_model.encode.call_count == 1
        _, kwargs = mock_model.encode.call_args
        assert kwargs.get("batch_size") == 32


class TestGenerateEmbeddings:
    @staticmethod
    def _silver_df(spark, include_null_row: bool = False):
        from pyspark.sql.types import (
            ArrayType,
            FloatType,
            StringType,
            StructField,
            StructType
        )
        schema = StructType([
            StructField("chunk_id", StringType()),
            StructField("document_id", StringType()),
            StructField("chunk_text", StringType()),
            StructField("classification", StringType()),
            StructField("allowed_roles", ArrayType(StringType())),
            StructField("owner", StringType()),
            StructField("department", StringType()),
            StructField("sensitivity_score", FloatType()),
            StructField("source_path", StringType()),
            StructField("version", StringType()),
            StructField("document_hash", StringType())
        ])
        data: list[tuple[str, str, str | None, str, list[str], str, str, float, str, str, str]] = [
            ("c1", "doc-1", "hello world", "public", ["reader"], "alice", "eng", 0.1, "/p", "1", "h")
        ]
        if include_null_row:
            data.append(("c2", "doc-1", None, "public", ["reader"], "alice", "eng", 0.1, "/p", "1", "h"))
        return spark.createDataFrame(data, schema=schema)

    @staticmethod
    def _patch_infra(dim: int = 384):
        return (
            patch("secure_semantic_docs.embeddings.chunk_embedder.configure_worker_environment"),
            patch(
                "secure_semantic_docs.embeddings.chunk_embedder.load_cached_model",
                return_value=_mock_model(dim=dim)
            )
        )

    def test_returns_dataframe_with_gold_schema(self, spark):
        from secure_semantic_docs.embeddings.chunk_embedder import generate_embeddings
        from secure_semantic_docs.models import Config, EmbeddingConfig

        cfg = Config(embedding=EmbeddingConfig(model="all-MiniLM-L6-v2", device="cpu", num_partitions=1))
        silver_df = self._silver_df(spark)

        with (
            patch("secure_semantic_docs.embeddings.chunk_embedder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.chunk_embedder.load_cached_model",
                  return_value=_mock_model(dim=384))
        ):
            gold_df = generate_embeddings(spark, silver_df, cfg)

        field_names = {f.name for f in gold_df.schema}
        assert {"chunk_id", "document_id", "embedding", "embedding_model", "embedding_created_at"} <= field_names

    def test_output_row_count_matches_input(self, spark):
        from secure_semantic_docs.embeddings.chunk_embedder import generate_embeddings
        from secure_semantic_docs.models import Config, EmbeddingConfig

        cfg = Config(embedding=EmbeddingConfig(device="cpu", num_partitions=1))
        silver_df = self._silver_df(spark)

        with (
            patch("secure_semantic_docs.embeddings.chunk_embedder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.chunk_embedder.load_cached_model",
                  return_value=_mock_model(dim=384))
        ):
            gold_df = generate_embeddings(spark, silver_df, cfg)

        assert gold_df.count() == silver_df.count()

    def test_null_chunk_text_rows_are_dropped(self, spark):
        from secure_semantic_docs.embeddings.chunk_embedder import generate_embeddings
        from secure_semantic_docs.models import Config, EmbeddingConfig

        cfg = Config(embedding=EmbeddingConfig(device="cpu", num_partitions=1))
        silver_df = self._silver_df(spark, include_null_row=True)
        assert silver_df.count() == 2

        with (
            patch("secure_semantic_docs.embeddings.chunk_embedder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.chunk_embedder.load_cached_model",
                  return_value=_mock_model(dim=384))
        ):
            gold_df = generate_embeddings(spark, silver_df, cfg)

        assert gold_df.count() == 1

    def test_uses_default_parallelism_when_num_partitions_zero(self, spark):
        from secure_semantic_docs.embeddings.chunk_embedder import generate_embeddings
        from secure_semantic_docs.models import Config, EmbeddingConfig

        cfg = Config(embedding=EmbeddingConfig(device="cpu", num_partitions=0))
        silver_df = self._silver_df(spark)

        with (
            patch("secure_semantic_docs.embeddings.chunk_embedder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.chunk_embedder.load_cached_model",
                  return_value=_mock_model(dim=384))
        ):
            gold_df = generate_embeddings(spark, silver_df, cfg)

        assert gold_df.count() == 1

    def test_loads_config_when_none_passed(self, spark):
        from secure_semantic_docs.embeddings.chunk_embedder import generate_embeddings
        from secure_semantic_docs.models import Config, EmbeddingConfig

        mock_cfg = Config(embedding=EmbeddingConfig(device="cpu", num_partitions=1))
        silver_df = self._silver_df(spark)

        with (
            patch("secure_semantic_docs.embeddings.chunk_embedder.load_config", return_value=mock_cfg),
            patch("secure_semantic_docs.embeddings.chunk_embedder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.chunk_embedder.load_cached_model",
                  return_value=_mock_model(dim=384))
        ):
            gold_df = generate_embeddings(spark, silver_df, config=None)

        assert gold_df.count() == 1


class TestGoldIngest:
    def test_ingest_reads_embeds_and_writes(self):
        mock_spark = MagicMock()
        mock_cfg = MagicMock()
        mock_silver_df = MagicMock()
        mock_gold_df = MagicMock()

        mock_cfg.readers.__getitem__.return_value.options = {"format": "delta", "path": "/silver"}
        mock_cfg.writers.__getitem__.return_value.options = {"format": "delta", "path": "/gold"}

        with (
            patch(
                "secure_semantic_docs.gold_ingestion.SparkReader"
            ) as mock_reader_cls,
            patch(
                "secure_semantic_docs.gold_ingestion.generate_embeddings",
                return_value=mock_gold_df
            ) as mock_gen,
            patch(
                "secure_semantic_docs.gold_ingestion.SparkWriter"
            ) as mock_writer_cls
        ):
            mock_reader_cls.return_value.read.return_value = mock_silver_df
            from secure_semantic_docs.gold_ingestion import ingest
            ingest(mock_spark, mock_cfg)

        mock_reader_cls.return_value.read.assert_called_once()
        mock_gen.assert_called_once_with(mock_spark, mock_silver_df, mock_cfg)
        mock_writer_cls.return_value.write.assert_called_once()

    def test_ingest_loads_config_when_none(self):
        mock_spark = MagicMock()
        mock_cfg = MagicMock()
        mock_cfg.readers.__getitem__.return_value.options = {}
        mock_cfg.writers.__getitem__.return_value.options = {}

        with (
            patch("secure_semantic_docs.gold_ingestion.load_config", return_value=mock_cfg) as mock_load,
            patch("secure_semantic_docs.gold_ingestion.SparkReader"),
            patch("secure_semantic_docs.gold_ingestion.generate_embeddings", return_value=MagicMock()),
            patch("secure_semantic_docs.gold_ingestion.SparkWriter")
        ):
            from secure_semantic_docs.gold_ingestion import ingest
            ingest(mock_spark, None)

        mock_load.assert_called_once()

    def test_main_calls_ingest_with_spark_and_config(self):
        mock_cfg = MagicMock()
        mock_spark = MagicMock()

        with (
            patch("secure_semantic_docs.gold_ingestion.configure_logging"),
            patch("secure_semantic_docs.gold_ingestion.load_config", return_value=mock_cfg),
            patch(
                "secure_semantic_docs.gold_ingestion.build_spark_session",
                return_value=mock_spark
            ) as mock_bs,
            patch("secure_semantic_docs.gold_ingestion.ingest") as mock_ingest
        ):
            from secure_semantic_docs.gold_ingestion import main
            main()

        mock_bs.assert_called_once_with(mock_cfg)
        mock_ingest.assert_called_once_with(mock_spark, mock_cfg)

    def test_main_suppresses_py4j_logs(self):
        with (
            patch("secure_semantic_docs.gold_ingestion.configure_logging"),
            patch("secure_semantic_docs.gold_ingestion.load_config", return_value=MagicMock()),
            patch("secure_semantic_docs.gold_ingestion.build_spark_session", return_value=MagicMock()),
            patch("secure_semantic_docs.gold_ingestion.ingest")
        ):
            from secure_semantic_docs.gold_ingestion import main
            main()

        assert logging.getLogger("py4j").level == logging.ERROR
