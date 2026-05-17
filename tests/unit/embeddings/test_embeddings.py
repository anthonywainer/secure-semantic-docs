"""Unit tests for the embeddings package and embedding ingestion."""

import logging
import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from pyspark.sql import Row
from pyspark.sql.types import StructField, StructType

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
        from secure_semantic_docs.core.spark_partitions import compute_partition_count
        return compute_partition_count(total_executor_cores, configured, is_local_mode)

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
            "chunk_span": Row(start=0, end=len(text.split())),
            "classification": "public",
            "allowed_roles": ["reader"],
            "owner": "alice",
            "department": "eng",
            "sensitivity_score": 0.1,
            "source_path": text,
            "version": "1",
            "document_hash": "abc",
            "chunk_text": text
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
    _TEST_KEY: bytes = b"\xab" * 32  # deterministic 32-byte key for tests

    @staticmethod
    def _call(
            rows: Iterator,
            model_name: str = "m",
            device: str = "cpu",
            batch_size: int = 32,
            normalize: bool = True,
            created_at: str = "2024-01-01T00:00:00Z",
            encryption_key: bytes = b"\xab" * 32,
            key_id: str = "test-key-id",
            embedding_dim: int = 4,
            embedding_dtype: str = "float32",
            raw_docs_dir: str = "unused"
    ) -> list:
        from secure_semantic_docs.embeddings.row_encoder import encode_and_encrypt_partition
        return list(encode_and_encrypt_partition(
            rows, model_name, device, batch_size, normalize,
            created_at, encryption_key, key_id, embedding_dim, embedding_dtype, raw_docs_dir
        ))

    def test_empty_partition_yields_nothing(self):
        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model", return_value=_mock_model()),
            patch("secure_semantic_docs.processing.document_reader.read_document_words",
                  side_effect=lambda source_path, raw_docs_dir: source_path.split())
        ):
            result = self._call(iter([]))
        assert result == []

    def test_returns_one_tuple_per_row(self):
        mock_model = _mock_model(dim=4)
        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model", return_value=mock_model),
            patch("secure_semantic_docs.processing.document_reader.read_document_words",
                  side_effect=lambda source_path, raw_docs_dir: source_path.split())
        ):
            result = self._call(_make_rows("hello", "world"))
        assert len(result) == 2

    def test_tuple_embedding_id_is_uuid_string(self):
        import re
        uuid_re = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        mock_model = _mock_model(dim=4)
        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model", return_value=mock_model),
            patch("secure_semantic_docs.processing.document_reader.read_document_words",
                  side_effect=lambda source_path, raw_docs_dir: source_path.split())
        ):
            result = self._call(_make_rows("hello"))
        assert uuid_re.match(result[0][0])

    def test_tuple_has_correct_chunk_id(self):
        mock_model = _mock_model(dim=4)
        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model", return_value=mock_model),
            patch("secure_semantic_docs.processing.document_reader.read_document_words",
                  side_effect=lambda source_path, raw_docs_dir: source_path.split())
        ):
            result = self._call(_make_rows("hello"))
        assert result[0][1] == "c0"

    def test_ciphertext_is_bytes(self):
        mock_model = _mock_model(dim=4)
        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model", return_value=mock_model),
            patch("secure_semantic_docs.processing.document_reader.read_document_words",
                  side_effect=lambda source_path, raw_docs_dir: source_path.split())
        ):
            result = self._call(_make_rows("hello"))
        ciphertext = result[0][3]
        assert isinstance(ciphertext, bytes)
        assert len(ciphertext) > 0

    def test_nonce_is_24_bytes(self):
        mock_model = _mock_model(dim=4)
        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model", return_value=mock_model),
            patch("secure_semantic_docs.processing.document_reader.read_document_words",
                  side_effect=lambda source_path, raw_docs_dir: source_path.split())
        ):
            result = self._call(_make_rows("hello"))
        nonce = result[0][4]
        assert isinstance(nonce, bytes)
        assert len(nonce) == 24

    def test_algorithm_label_correct(self):
        mock_model = _mock_model(dim=4)
        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model", return_value=mock_model),
            patch("secure_semantic_docs.processing.document_reader.read_document_words",
                  side_effect=lambda source_path, raw_docs_dir: source_path.split())
        ):
            result = self._call(_make_rows("hello"))
        assert result[0][5] == "XSalsa20-Poly1305"

    def test_embedding_dim_stored(self):
        mock_model = _mock_model(dim=4)
        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model", return_value=mock_model),
            patch("secure_semantic_docs.processing.document_reader.read_document_words",
                  side_effect=lambda source_path, raw_docs_dir: source_path.split())
        ):
            result = self._call(_make_rows("hello"), embedding_dim=4)
        assert result[0][6] == 4

    def test_model_name_stamped_on_row(self):
        mock_model = _mock_model(dim=4)
        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model", return_value=mock_model),
            patch("secure_semantic_docs.processing.document_reader.read_document_words",
                  side_effect=lambda source_path, raw_docs_dir: source_path.split())
        ):
            result = self._call(_make_rows("hello"), model_name="my-model")
        assert result[0][8] == "my-model"

    def test_key_id_stamped_on_row(self):
        mock_model = _mock_model(dim=4)
        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model", return_value=mock_model),
            patch("secure_semantic_docs.processing.document_reader.read_document_words",
                  side_effect=lambda source_path, raw_docs_dir: source_path.split())
        ):
            result = self._call(_make_rows("hello"), key_id="my-key-id")
        assert result[0][9] == "my-key-id"

    def test_created_at_stamped_on_row(self):
        mock_model = _mock_model(dim=4)
        ts = "2024-06-01T12:00:00Z"
        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model", return_value=mock_model),
            patch("secure_semantic_docs.processing.document_reader.read_document_words",
                  side_effect=lambda source_path, raw_docs_dir: source_path.split())
        ):
            result = self._call(_make_rows("hello"), created_at=ts)
        assert result[0][17] == ts

    def test_ciphertext_decryptable(self):
        from secure_semantic_docs.embeddings.serializer import bytes_to_embedding
        from secure_semantic_docs.security.keyring_store import generate_secret_key
        from secure_semantic_docs.security.secretbox_decryptor import secretbox_decrypt
        key = generate_secret_key()
        mock_model = _mock_model(dim=4)
        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model", return_value=mock_model),
            patch("secure_semantic_docs.processing.document_reader.read_document_words",
                  side_effect=lambda source_path, raw_docs_dir: source_path.split())
        ):
            result = self._call(_make_rows("hello"), encryption_key=key, embedding_dim=4)
        ciphertext, nonce = result[0][3], result[0][4]
        raw = secretbox_decrypt(ciphertext, nonce, key)
        arr = bytes_to_embedding(raw, dim=4)
        assert arr.shape == (4,)

    def test_encode_failure_raises_embedding_error(self):
        failing_model = MagicMock()
        failing_model.encode.side_effect = RuntimeError("GPU OOM")
        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model", return_value=failing_model)
        ):
            with pytest.raises(EmbeddingError, match="Batch encode failed"):
                self._call(_make_rows("hello"))

    def test_calls_encode_once_for_full_partition(self):
        mock_model = _mock_model(dim=4)
        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model", return_value=mock_model),
            patch("secure_semantic_docs.processing.document_reader.read_document_words",
                  side_effect=lambda source_path, raw_docs_dir: source_path.split())
        ):
            self._call(_make_rows("a", "b", "c"))
        assert mock_model.encode.call_count == 1
        _, kwargs = mock_model.encode.call_args
        assert kwargs.get("batch_size") == 32

    def test_encodes_transient_chunk_text_without_source_read(self):
        mock_model = _mock_model(dim=4)
        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model", return_value=mock_model),
            patch(
                "secure_semantic_docs.processing.chunk_texts.read_document_words",
                side_effect=AssertionError("source document should not be read")
            )
        ):
            self._call(_make_rows("transient text"))

        texts, _ = mock_model.encode.call_args
        assert texts == (["transient text"],)


class TestChunkTexts:
    def test_uses_transient_chunk_text(self):
        from secure_semantic_docs.processing.chunk_texts import chunk_texts

        rows = [{"chunk_text": "cached text", "source_path": "doc.txt"}]
        with patch(
                "secure_semantic_docs.processing.chunk_texts.read_document_words",
                side_effect=AssertionError("source document should not be read")
        ):
            assert chunk_texts(rows, "unused") == ["cached text"]

    def test_reconstructs_text_from_source_span(self):
        from secure_semantic_docs.processing.chunk_texts import chunk_texts

        rows = [
            {
                "chunk_span": Row(start=1, end=4),
                "source_path": "doc.txt"
            }
        ]
        with patch(
                "secure_semantic_docs.processing.chunk_texts.read_document_words",
                return_value=["zero", "one", "two", "three", "four"]
        ) as mock_reader:
            assert chunk_texts(rows, "/raw") == ["one two three"]

        mock_reader.assert_called_once_with("doc.txt", "/raw")

    def test_reuses_source_words_for_same_document(self):
        from secure_semantic_docs.processing.chunk_texts import chunk_texts

        rows = [
            {"chunk_span": Row(start=0, end=2), "source_path": "doc.txt"},
            {"chunk_span": Row(start=2, end=4), "source_path": "doc.txt"}
        ]
        with patch(
                "secure_semantic_docs.processing.chunk_texts.read_document_words",
                return_value=["zero", "one", "two", "three"]
        ) as mock_reader:
            assert chunk_texts(rows, "/raw") == ["zero one", "two three"]

        mock_reader.assert_called_once_with("doc.txt", "/raw")

    def test_missing_span_reads_empty_slice(self):
        from secure_semantic_docs.processing.chunk_texts import chunk_texts

        rows = [{"source_path": "doc.txt"}]
        with patch(
                "secure_semantic_docs.processing.chunk_texts.read_document_words",
                return_value=["zero", "one"]
        ) as mock_reader:
            assert chunk_texts(rows, "/raw") == [""]

        mock_reader.assert_called_once_with("doc.txt", "/raw")


class TestGenerateEmbeddings:
    @staticmethod
    def _setup_raw_doc(tmp_path, filename: str = "doc-1.txt", text: str = "hello world") -> str:
        raw_docs_dir = tmp_path / "synthetic_data" / "raw_documents"
        raw_docs_dir.mkdir(parents=True, exist_ok=True)
        (raw_docs_dir / filename).write_text(text, encoding="utf-8")
        return filename

    @staticmethod
    def _chunks_df(spark, source_path: str, include_null_row: bool = False):
        from pyspark.sql.types import StructType

        schema = StructType.fromDDL(
            "chunk_id string, document_id string, chunk_span struct<start:int,end:int>, "
            "classification string, allowed_roles array<string>, owner string, "
            "department string, sensitivity_score float, source_path string, "
            "version string, document_hash string"
        )
        data: list[tuple[
            str,
            str,
            Row | None,
            str,
            list[str],
            str,
            str,
            float,
            str,
            str,
            str
        ]] = [
            ("c1", "doc-1", Row(start=0, end=2), "public", ["reader"], "alice", "eng", 0.1, source_path, "1", "h")
        ]
        if include_null_row:
            data.append(("c2", "doc-1", None, "public", ["reader"], "alice", "eng", 0.1, source_path, "1", "h"))
        return spark.createDataFrame(data, schema=schema)

    def test_returns_dataframe_with_embedding_schema(self, spark, tmp_path):
        from secure_semantic_docs.embeddings.core import generate_embeddings
        from secure_semantic_docs.models import Config, EmbeddingConfig
        from secure_semantic_docs.security.keyring_store import generate_secret_key

        test_key = generate_secret_key()
        source_path = self._setup_raw_doc(tmp_path)
        cfg = Config(project_root=tmp_path,
                     embedding=EmbeddingConfig(model="all-MiniLM-L6-v2", device="cpu", num_partitions=1))
        chunks_df = self._chunks_df(spark, source_path)

        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model",
                  return_value=_mock_model(dim=384)),
            patch("secure_semantic_docs.models.embedding_model.resolve_key_material",
                  return_value=(test_key, "test-key-id"))
        ):
            embeddings_df = generate_embeddings(spark, chunks_df, cfg)

        field_names = {f.name for f in embeddings_df.schema}
        assert {
                   "embedding_id", "chunk_id", "document_id",
                   "embedding_ciphertext", "embedding_nonce", "embedding_model", "created_at"
               } <= field_names

    def test_output_row_count_matches_input(self, spark, tmp_path):
        from secure_semantic_docs.embeddings.core import generate_embeddings
        from secure_semantic_docs.models import Config, EmbeddingConfig
        from secure_semantic_docs.security.keyring_store import generate_secret_key

        test_key = generate_secret_key()
        source_path = self._setup_raw_doc(tmp_path)
        cfg = Config(project_root=tmp_path, embedding=EmbeddingConfig(device="cpu", num_partitions=1))
        chunks_df = self._chunks_df(spark, source_path)

        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model",
                  return_value=_mock_model(dim=384)),
            patch("secure_semantic_docs.models.embedding_model.resolve_key_material",
                  return_value=(test_key, "test-key-id"))
        ):
            embeddings_df = generate_embeddings(spark, chunks_df, cfg)

        assert embeddings_df.count() == chunks_df.count()

    def test_null_chunk_span_rows_are_dropped(self, spark, tmp_path):
        from secure_semantic_docs.embeddings.core import generate_embeddings
        from secure_semantic_docs.models import Config, EmbeddingConfig
        from secure_semantic_docs.security.keyring_store import generate_secret_key

        test_key = generate_secret_key()
        source_path = self._setup_raw_doc(tmp_path)
        cfg = Config(project_root=tmp_path, embedding=EmbeddingConfig(device="cpu", num_partitions=1))
        chunks_df = self._chunks_df(spark, source_path, include_null_row=True)
        assert chunks_df.count() == 2

        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model",
                  return_value=_mock_model(dim=384)),
            patch("secure_semantic_docs.models.embedding_model.resolve_key_material",
                  return_value=(test_key, "test-key-id"))
        ):
            embeddings_df = generate_embeddings(spark, chunks_df, cfg)

        assert embeddings_df.count() == 1

    def test_uses_default_parallelism_when_num_partitions_zero(self, spark, tmp_path):
        from secure_semantic_docs.embeddings.core import generate_embeddings
        from secure_semantic_docs.models import Config, EmbeddingConfig
        from secure_semantic_docs.security.keyring_store import generate_secret_key

        test_key = generate_secret_key()
        source_path = self._setup_raw_doc(tmp_path)
        cfg = Config(project_root=tmp_path, embedding=EmbeddingConfig(device="cpu", num_partitions=0))
        chunks_df = self._chunks_df(spark, source_path)

        with (
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model",
                  return_value=_mock_model(dim=384)),
            patch("secure_semantic_docs.models.embedding_model.resolve_key_material",
                  return_value=(test_key, "test-key-id"))
        ):
            embeddings_df = generate_embeddings(spark, chunks_df, cfg)

        assert embeddings_df.count() == 1

    def test_loads_config_when_none_passed(self, spark, tmp_path):
        from secure_semantic_docs.embeddings.core import generate_embeddings
        from secure_semantic_docs.models import Config, EmbeddingConfig
        from secure_semantic_docs.security.keyring_store import generate_secret_key

        test_key = generate_secret_key()
        source_path = self._setup_raw_doc(tmp_path)
        mock_cfg = Config(project_root=tmp_path, embedding=EmbeddingConfig(device="cpu", num_partitions=1))
        chunks_df = self._chunks_df(spark, source_path)

        with (
            patch("secure_semantic_docs.embeddings.core.load_config", return_value=mock_cfg),
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model",
                  return_value=_mock_model(dim=384)),
            patch("secure_semantic_docs.models.embedding_model.resolve_key_material",
                  return_value=(test_key, "test-key-id"))
        ):
            embeddings_df = generate_embeddings(spark, chunks_df, config=None)

        assert embeddings_df.count() == 1


class TestResolveEmbeddingSettings:
    @staticmethod
    def _spark(master: str = "local[*]", default_parallelism: int = 4):
        mock_spark = MagicMock()
        mock_spark.sparkContext.master = master
        mock_spark.sparkContext.defaultParallelism = default_parallelism
        return mock_spark

    def test_uses_raw_documents_reader_path(self, tmp_path):
        from secure_semantic_docs.models import Config, EmbeddingConfig, ReaderEntry, ReadersConfig
        from secure_semantic_docs.models.embedding_model import resolve_embedding_settings

        config = Config(
            project_root=tmp_path,
            readers=ReadersConfig(entries={
                "raw_documents": ReaderEntry(options={"path": "/configured/raw"})
            }),
            embedding=EmbeddingConfig(device="cpu", num_partitions=3)
        )

        with patch(
                "secure_semantic_docs.models.embedding_model.resolve_key_material",
                return_value=(b"\x01" * 32, "key-1")
        ):
            settings = resolve_embedding_settings(
                self._spark(master="spark://cluster", default_parallelism=8),
                config
            )

        assert settings.raw_docs_dir == "/configured/raw"
        assert settings.num_partitions == 3
        assert settings.is_local_mode is False
        assert settings.key_id == "key-1"

    def test_falls_back_to_config_raw_documents_dir_without_reader(self, tmp_path):
        from secure_semantic_docs.models import Config, EmbeddingConfig
        from secure_semantic_docs.models.embedding_model import resolve_embedding_settings

        config = Config(
            project_root=tmp_path,
            embedding=EmbeddingConfig(device="cpu", num_partitions=0)
        )

        with patch(
                "secure_semantic_docs.models.embedding_model.resolve_key_material",
                return_value=(b"\x02" * 32, "key-2")
        ):
            settings = resolve_embedding_settings(self._spark(), config)

        assert settings.raw_docs_dir == str(config.raw_documents_dir)
        assert settings.num_partitions == 1
        assert settings.is_local_mode is True

    def test_falls_back_when_reader_has_no_path(self, tmp_path):
        from secure_semantic_docs.models import Config, ReaderEntry, ReadersConfig
        from secure_semantic_docs.models.embedding_model import resolve_embedding_settings

        config = Config(
            project_root=tmp_path,
            readers=ReadersConfig(entries={
                "raw_documents": ReaderEntry(options={"format": "text"})
            })
        )

        with patch(
                "secure_semantic_docs.models.embedding_model.resolve_key_material",
                return_value=(b"\x03" * 32, "key-3")
        ):
            settings = resolve_embedding_settings(self._spark(), config)

        assert settings.raw_docs_dir == str(config.raw_documents_dir)

    def test_resolve_key_material_delegates_to_keyring_store(self):
        from secure_semantic_docs.models.embedding_model import resolve_key_material

        config = MagicMock()
        with patch(
                "secure_semantic_docs.security.keyring_store.resolve_key_material",
                return_value=(b"\x04" * 32, "key-4")
        ) as mock_resolver:
            assert resolve_key_material(config) == (b"\x04" * 32, "key-4")

        mock_resolver.assert_called_once_with(config)


class TestEmbeddingIngest:
    def test_ingest_reads_embeds_and_writes(self):
        mock_spark = MagicMock()
        mock_cfg = MagicMock()
        mock_documents_df = MagicMock()
        mock_workset_df = MagicMock()
        mock_facts_df = MagicMock()
        mock_embeddings_df = MagicMock()

        mock_cfg.project_root = Path("/project")
        mock_cfg.readers.__getitem__.return_value.options = {"format": "delta", "path": "/chunks"}
        mock_cfg.writers.__getitem__.return_value.options = {"format": "delta", "path": "/embeddings"}
        mock_facts_df.collect.return_value = []

        with (
            patch(
                "secure_semantic_docs.gold_ingestion.SparkReader"
            ) as mock_reader_cls,
            patch(
                "secure_semantic_docs.gold_ingestion.create_chunk_workset",
                return_value=mock_workset_df
            ) as mock_workset,
            patch(
                "secure_semantic_docs.gold_ingestion.select_persisted_chunk_columns",
                return_value=MagicMock()
            ),
            patch(
                "secure_semantic_docs.gold_ingestion.generate_embeddings",
                return_value=mock_embeddings_df
            ) as mock_gen,
            patch(
                "secure_semantic_docs.gold_ingestion.extract_facts_df_document_aware",
                return_value=mock_facts_df
            ) as mock_extract_facts,
            patch(
                "secure_semantic_docs.gold_ingestion.write_facts_jsonl"
            ),
            patch(
                "secure_semantic_docs.gold_ingestion.SparkWriter"
            ) as mock_writer_cls
        ):
            mock_workset_df.persist.return_value = mock_workset_df
            mock_reader_cls.return_value.read.return_value = mock_documents_df
            from secure_semantic_docs.gold_ingestion import ingest
            ingest(mock_spark, mock_cfg)

        mock_reader_cls.return_value.read.assert_called_once()
        mock_workset.assert_called_once_with(mock_spark, mock_documents_df, mock_cfg)
        mock_extract_facts.assert_called_once()
        mock_gen.assert_called_once_with(mock_spark, mock_workset_df, mock_cfg)
        assert mock_writer_cls.return_value.write.call_count == 2
        mock_facts_df.unpersist.assert_called_once()
        mock_workset_df.unpersist.assert_called_once()

    def test_ingest_loads_config_when_none(self):
        mock_spark = MagicMock()
        mock_cfg = MagicMock()
        mock_cfg.readers.__getitem__.return_value.options = {}
        mock_cfg.writers.__getitem__.return_value.options = {}

        with (
            patch("secure_semantic_docs.gold_ingestion.load_config", return_value=mock_cfg) as mock_load,
            patch("secure_semantic_docs.gold_ingestion.SparkReader"),
            patch("secure_semantic_docs.gold_ingestion.create_chunk_workset", return_value=MagicMock()),
            patch("secure_semantic_docs.gold_ingestion.select_persisted_chunk_columns", return_value=MagicMock()),
            patch("secure_semantic_docs.gold_ingestion.generate_embeddings", return_value=MagicMock()),
            patch("secure_semantic_docs.gold_ingestion.extract_facts_df_document_aware", return_value=MagicMock()),
            patch("secure_semantic_docs.gold_ingestion.write_facts_jsonl"),
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


class TestBuildCachedEmbeddings:
    @staticmethod
    def _chunks_df_with_cache(spark, source_path: str):
        from pyspark.sql.types import StructType
        schema = StructType.fromDDL(
            "chunk_id string, document_id string, chunk_span struct<start:int,end:int>, "
            "classification string, allowed_roles array<string>, owner string, "
            "department string, sensitivity_score float, source_path string, "
            "version string, document_hash string, "
            "embedding_ciphertext binary, embedding_nonce binary, "
            "embedding_algorithm string, embedding_dim int, key_id string, model string"
        )
        return spark.createDataFrame(
            [(
                "c1", "doc-1", Row(start=0, end=2), "public", ["reader"], "alice", "eng",
                0.1, source_path, "1", "hash-a",
                b"cipher", b"nonce" * 5, "XSalsa20", 384, "test-key-id", "model-1"
            )],
            schema=schema
        )

    def test_returns_embedding_schema(self, spark, tmp_path):
        from secure_semantic_docs.embeddings.cache_rows import build_cached_embeddings
        from secure_semantic_docs.storage.schemas import load_schema

        raw_docs_dir = tmp_path / "synthetic_data" / "raw_documents"
        raw_docs_dir.mkdir(parents=True, exist_ok=True)
        (raw_docs_dir / "doc-1.txt").write_text("hello world", encoding="utf-8")
        source_path = "doc-1.txt"

        hits_df = self._chunks_df_with_cache(spark, source_path)
        embedding_schema = load_schema("gold_embeddings")

        result = build_cached_embeddings(
            hits_df,
            "test-key-id",
            "2024-01-01T00:00:00Z",
            embedding_schema
        )

        assert result.count() == 1
        assert _field_names(embedding_schema) == {f.name for f in result.schema}

    def test_excludes_different_key(self, spark, tmp_path):
        from secure_semantic_docs.embeddings.cache_rows import build_cached_embeddings
        from secure_semantic_docs.storage.schemas import load_schema

        raw_docs_dir = tmp_path / "synthetic_data" / "raw_documents"
        raw_docs_dir.mkdir(parents=True, exist_ok=True)
        (raw_docs_dir / "doc-1.txt").write_text("hello world", encoding="utf-8")
        source_path = "doc-1.txt"

        hits_df = self._chunks_df_with_cache(spark, source_path)
        embedding_schema = load_schema("gold_embeddings")

        result = build_cached_embeddings(
            hits_df,
            "different-key-id",
            "2024-01-01T00:00:00Z",
            embedding_schema
        )
        assert result.count() == 0

    def test_generate_embeddings_uses_cache_hits(self, spark, tmp_path):
        from secure_semantic_docs.embeddings.core import generate_embeddings
        from secure_semantic_docs.models import Config, EmbeddingConfig
        from secure_semantic_docs.security.keyring_store import generate_secret_key

        raw_docs_dir = tmp_path / "synthetic_data" / "raw_documents"
        raw_docs_dir.mkdir(parents=True, exist_ok=True)
        (raw_docs_dir / "doc-1.txt").write_text("hello world", encoding="utf-8")
        source_path = "doc-1.txt"

        test_key = generate_secret_key()
        cfg = Config(project_root=tmp_path, embedding=EmbeddingConfig(device="cpu", num_partitions=1))

        from pyspark.sql.types import StructType
        chunk_schema = StructType.fromDDL(
            "chunk_id string, document_id string, chunk_span struct<start:int,end:int>, "
            "classification string, allowed_roles array<string>, owner string, "
            "department string, sensitivity_score float, source_path string, "
            "version string, document_hash string"
        )
        chunks_df = spark.createDataFrame(
            [("c1", "doc-1", Row(start=0, end=2), "public", ["reader"], "alice", "eng",
              0.1, source_path, "1", "hash-a")],
            schema=chunk_schema
        )

        cache_schema = StructType.fromDDL(
            "chunk_id string, document_hash string, "
            "embedding_ciphertext binary, embedding_nonce binary, "
            "embedding_algorithm string, embedding_dim int, key_id string, model string"
        )
        mock_cache_df = spark.createDataFrame(
            [("c1", "hash-a", b"cipher", b"nonce" * 5, "XSalsa20", 384, "test-key-id", "m1")],
            schema=cache_schema
        )

        with (
            patch("secure_semantic_docs.embeddings.core.load_cache", return_value=mock_cache_df),
            patch("secure_semantic_docs.embeddings.row_encoder.configure_worker_environment"),
            patch("secure_semantic_docs.embeddings.row_encoder.load_cached_model",
                  return_value=_mock_model(dim=384)),
            patch("secure_semantic_docs.models.embedding_model.resolve_key_material",
                  return_value=(test_key, "test-key-id")),
            patch("secure_semantic_docs.embeddings.core.write_cache")
        ):
            result_df = generate_embeddings(spark, chunks_df, cfg)

        assert result_df.count() >= 1


def _field_names(schema: StructType) -> set[str]:
    fields: list[StructField] = list(schema.fields or [])
    return {field.name for field in fields}
