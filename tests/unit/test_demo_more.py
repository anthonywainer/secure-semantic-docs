from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import secure_semantic_docs.demo as demo
from secure_semantic_docs.loader import Config


def _config(project_root: Path, secret_key_env_var: str = "DOCSEC_SECRET_KEY") -> Config:
    return Config(project_root=project_root, secret_key_env_var=secret_key_env_var)


def test_main_exits_when_required_task_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        demo,
        "run_demo_pipeline",
        lambda: [demo.TaskResult("x", "failed", True, 0.0, "boom")]
    )

    with pytest.raises(SystemExit) as exc_info:
        demo.main()

    assert exc_info.value.code == 1


def test_task_prepare_runtime_dirs_creates_expected_directories(tmp_path: Path) -> None:
    config = _config(tmp_path)

    demo.task_prepare_runtime_dirs(config)

    expected = [
        config.lakehouse_dir,
        config.bronze_dir,
        config.lakehouse_dir / "silver_chunks",
        config.lakehouse_dir / "gold_embeddings",
        config.logs_dir,
        config.project_root / "runtime" / "metadata",
        config.project_root / "runtime" / "vector_store" / "chroma"
    ]
    assert all(path.exists() for path in expected)


def test_task_validate_configuration_success_and_failures(tmp_path: Path) -> None:
    config = _config(tmp_path)
    tmp_path.mkdir(exist_ok=True)
    demo.task_validate_configuration(config)

    missing_root = tmp_path / "missing-root"
    with pytest.raises(RuntimeError, match="Project root does not exist"):
        demo.task_validate_configuration(_config(missing_root))

    with pytest.raises(RuntimeError, match="Secret key environment variable"):
        demo.task_validate_configuration(_config(tmp_path, secret_key_env_var=""))


def test_task_validate_input_data_handles_missing_empty_and_valid(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with pytest.raises(RuntimeError, match="Raw documents directory not found"):
        demo.task_validate_input_data(config)

    config.raw_documents_dir.mkdir(parents=True)
    with pytest.raises(RuntimeError, match=r"No \.txt document files found"):
        demo.task_validate_input_data(config)

    (config.raw_documents_dir / "example.txt").write_text("hello", encoding="utf-8")
    demo.task_validate_input_data(config)


def test_task_run_ingestion_steps_invoke_module_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path
) -> None:
    called: list[str] = []

    monkeypatch.setattr("secure_semantic_docs.bronze_ingestion.main", lambda: called.append("bronze"))
    monkeypatch.setattr("secure_semantic_docs.silver_ingestion.main", lambda: called.append("silver"))
    monkeypatch.setattr("secure_semantic_docs.gold_ingestion.main", lambda: called.append("gold"))

    config = _config(tmp_path)
    demo.task_run_bronze_ingestion(config)
    demo.task_run_silver_ingestion(config)
    demo.task_run_gold_ingestion(config)

    assert called == ["bronze", "silver", "gold"]


def test_task_build_graph_or_facts_loads_records(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path
) -> None:
    recorded: dict[str, Path] = {}

    def fake_load(path: Path) -> list[dict[str, str]]:
        recorded["path"] = path
        return [{"fact_id": "f1"}, {"fact_id": "f2"}]

    monkeypatch.setattr(
        "secure_semantic_docs.serving.retrieval_service.load_fact_records",
        fake_load
    )

    demo.task_build_graph_or_facts(_config(tmp_path))

    assert recorded["path"] == (
        tmp_path / "runtime" / "metadata" / "facts" / "extracted_facts.jsonl"
    )


def test_decode_chroma_embeddings_filters_and_decrypts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path
) -> None:
    config = _config(tmp_path)
    valid_record = {
        "chunk_id": "c1",
        "embedding_ciphertext": b"cipher",
        "embedding_nonce": b"nonce",
        "embedding_dim": 2,
        "embedding_dtype": "float32"
    }
    monkeypatch.setattr(
        "secure_semantic_docs.security.keyring_store.resolve_secret_key",
        lambda _cfg: b"key"
    )
    monkeypatch.setattr(
        "secure_semantic_docs.security.secretbox_decryptor.secretbox_decrypt",
        lambda ciphertext, nonce, key: b"payload"
    )
    monkeypatch.setattr(
        "secure_semantic_docs.embeddings.serializer.bytes_to_embedding",
        lambda data, dim, dtype: np.array([1.0, 2.0], dtype=np.float32)
    )

    records, embeddings = demo._decode_chroma_embeddings(
        config,
        [
            {"chunk_id": "missing-cipher", "embedding_nonce": b"nonce", "embedding_dim": 2},
            {"chunk_id": "missing-nonce", "embedding_ciphertext": b"cipher", "embedding_dim": 2},
            {"chunk_id": "missing-dim", "embedding_ciphertext": b"cipher", "embedding_nonce": b"nonce"},
            valid_record
        ]
    )

    assert records == [valid_record]
    assert embeddings == [[1.0, 2.0]]



def test_task_sync_chroma_index_handles_empty_and_non_empty_records(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path
) -> None:
    empty_calls: list[str] = []

    monkeypatch.setattr(
        "secure_semantic_docs.governance.retrieval.load_gold_records",
        lambda path: []
    )
    monkeypatch.setattr(
        "secure_semantic_docs.vector_store.chroma_client.connect_chroma",
        lambda: "client"
    )
    monkeypatch.setattr(demo, "_decode_chroma_embeddings", lambda config, records: (records, [[0.1, 0.2] for _ in records]))
    monkeypatch.setattr(
        "secure_semantic_docs.vector_store.chroma_client.upsert_candidates",
        lambda client, records, embeddings: empty_calls.append("upsert") or 0
    )

    demo.task_sync_chroma_index(_config(tmp_path))
    assert empty_calls == []

    skipped_calls: list[str] = []
    monkeypatch.setattr(
        "secure_semantic_docs.governance.retrieval.load_gold_records",
        lambda path: [{"chunk_id": "blocked"}]
    )
    monkeypatch.setattr(demo, "_decode_chroma_embeddings", lambda config, records: ([], []))
    monkeypatch.setattr(
        "secure_semantic_docs.vector_store.chroma_client.upsert_candidates",
        lambda client, records, embeddings: skipped_calls.append("upsert") or 0
    )
    demo.task_sync_chroma_index(_config(tmp_path))
    assert skipped_calls == []

    captured: dict[str, object] = {}

    def fake_upsert(client: object, records: list[dict[str, str]], embeddings: list[list[float]]) -> int:
        captured["client"] = client
        captured["records"] = records
        captured["embeddings"] = embeddings
        return 1

    monkeypatch.setattr(
        "secure_semantic_docs.governance.retrieval.load_gold_records",
        lambda path: [{"chunk_id": "c1"}]
    )
    monkeypatch.setattr(demo, "_decode_chroma_embeddings", lambda config, records: (records, [[0.1, 0.2] for _ in records]))
    monkeypatch.setattr(
        "secure_semantic_docs.vector_store.chroma_client.upsert_candidates",
        fake_upsert
    )

    demo.task_sync_chroma_index(_config(tmp_path))

    assert captured == {"client": "client", "records": [{"chunk_id": "c1"}], "embeddings": [[0.1, 0.2]]}


def test_task_export_openmetadata_delegates_to_exporter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path
) -> None:
    captured: dict[str, Path] = {}

    def fake_export(output_path: Path, project_root: Path) -> None:
        captured["output_path"] = output_path
        captured["project_root"] = project_root

    monkeypatch.setattr("secure_semantic_docs.governance.export_openmetadata_catalog", fake_export)

    config = _config(tmp_path)
    config.logs_dir.mkdir(parents=True)
    demo.task_export_openmetadata(config)

    assert captured["output_path"] == config.logs_dir / "openmetadata_assets.json"
    assert captured["project_root"] == config.project_root


def test_task_run_quality_checks_writes_report_and_logs_warnings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path
) -> None:
    report = {
        "status": "failed",
        "passed": 1,
        "total": 2,
        "warnings": ["missing owner", "missing key_id"]
    }
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "secure_semantic_docs.governance.validate_metadata_quality",
        lambda bronze, silver, gold: report
    )

    def fake_write_quality_report(payload: dict[str, object], output: Path) -> None:
        captured["payload"] = payload
        captured["output"] = output

    monkeypatch.setattr("secure_semantic_docs.governance.write_quality_report", fake_write_quality_report)

    config = _config(tmp_path)
    demo.task_run_quality_checks(config)

    assert captured["payload"] is report
    assert captured["output"] == config.logs_dir / "metadata_quality_report.json"
