from __future__ import annotations

import builtins
import json
from pathlib import Path

import numpy as np
import pytest

import secure_semantic_docs.governance.quality as quality
from secure_semantic_docs.governance.contracts import Contracts, DatasetContract


def _dataset_contract(dataset_id: str, layer: str, required: list[str], forbidden: list[str]) -> DatasetContract:
    return DatasetContract(
        id=dataset_id,
        name=dataset_id,
        layer=layer,
        owner="platform",
        description=f"Contract for {dataset_id}",
        classification="internal",
        tags=[],
        fields=[],
        required_fields=required,
        sensitive_fields=[],
        forbidden_fields=forbidden,
        lineage_upstream=[],
        lineage_downstream=[],
        security_notes="",
        sensitive_flags={}
    )


def test_load_parquet_records_handles_missing_directory_no_files_and_success(tmp_path: Path) -> None:
    assert quality._load_parquet_records(tmp_path / "missing") == []

    layer = tmp_path / "layer"
    layer.mkdir()
    assert quality._load_parquet_records(layer) == []

    import pandas as pd

    success_layer = tmp_path / "success"
    success_layer.mkdir()
    pd.DataFrame([{"document_id": "DOC-1"}]).to_parquet(success_layer / "part.parquet", index=False)
    assert quality._load_parquet_records(success_layer) == [{"document_id": "DOC-1"}]


def test_load_parquet_records_handles_read_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    layer = tmp_path / "layer"
    layer.mkdir()
    (layer / "part.parquet").write_text("placeholder", encoding="utf-8")

    import pandas as pd

    monkeypatch.setattr(pd, "read_parquet", lambda path: (_ for _ in ()).throw(ValueError("bad parquet")))
    assert quality._load_parquet_records(layer) == []


def test_is_empty_value_handles_numpy_arrays_and_import_error(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    assert quality._is_empty_value(None) is True
    assert quality._is_empty_value(np.array([])) is True
    assert quality._is_empty_value(np.array([1])) is False

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "numpy":
            raise ImportError("numpy unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert quality._is_empty_value(()) is True
    assert quality._is_empty_value("value") is False


def test_required_check_helpers_cover_success_failure_and_empty_records() -> None:
    assert quality._count_non_null([{"field": "x"}, {"field": None}], "field") == (2, 1)
    assert quality._required_check_name("custom", "owner") == "custom_have_owner"

    checks: dict[str, bool] = {}
    failed: list[str] = []
    quality._run_check(checks, failed, [], "empty", "field", "unused")
    assert checks == {}

    quality._run_check(checks, failed, [{"field": "x"}, {"field": ""}], "has_field", "field", "{missing}/{total} missing")
    assert checks["has_field"] is False
    assert failed == ["1/2 missing"]


def test_check_no_forbidden_fields_covers_empty_and_exposed_records() -> None:
    checks: dict[str, bool] = {}
    failed: list[str] = []

    quality._check_no_forbidden_fields(checks, failed, [], "ui_view", ["secret"])
    assert checks["ui_view_no_secret"] is True

    quality._check_no_forbidden_fields(
        checks,
        failed,
        [{"secret": "x"}, {"secret": None}],
        "ui_view",
        ["secret"]
    )
    assert checks["ui_view_no_secret"] is False
    assert failed[-1] == "ui_view: 1/2 records expose forbidden field 'secret'"


def test_validate_metadata_quality_from_contracts_exercises_branching(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path
) -> None:
    contracts = Contracts(
        datasets={
            "bronze_documents": _dataset_contract(
                "bronze_documents",
                "bronze",
                ["classification", "owner"],
                []
            ),
            "silver_chunks": _dataset_contract(
                "silver_chunks",
                "silver",
                ["document_id", "classification"],
                []
            ),
            "gold_embeddings": _dataset_contract(
                "gold_embeddings",
                "gold",
                ["chunk_id", "document_id", "classification"],
                []
            ),
            "ui_view": _dataset_contract("ui_view", "ui", ["document_id"], ["secret"])
        },
        roles={},
        classifications={},
        access_policies={},
        lineage=[]
    )

    monkeypatch.setattr(quality, "load_contracts", lambda contracts_dir=None: contracts)
    monkeypatch.setattr(
        quality,
        "_load_dataset_records",
        lambda dataset_paths: {
            "bronze_documents": [{"classification": "internal", "owner": None}],
            "silver_chunks": [
                {"document_id": "doc-1", "classification": "confidential", "allowed_roles": []}
            ],
            "gold_embeddings": [
                {
                    "chunk_id": "chunk-1",
                    "document_id": "doc-1",
                    "classification": "internal",
                    "key_id": None
                }
            ],
            "ui_view": [{"document_id": "doc-1", "secret": "present"}],
            "unknown_dataset": []
        }
    )

    report = quality.validate_metadata_quality_from_contracts(
        {
            "bronze_documents": tmp_path / "bronze",
            "silver_chunks": tmp_path / "silver",
            "gold_embeddings": tmp_path / "gold",
            "ui_view": tmp_path / "ui",
            "unknown_dataset": tmp_path / "unknown"
        }
    )

    assert report["status"] == "failed"
    assert report["checks"]["bronze_documents_have_owner"] is False
    assert report["checks"]["silver_chunks_confidential_have_allowed_roles"] is False
    assert report["checks"]["gold_embeddings_have_encryption_metadata"] is False
    assert report["checks"]["gold_embeddings_no_plaintext_vectors"] is True
    assert report["checks"]["ui_view_no_secret"] is False
    assert any("No unknown records found" in warning for warning in report["warnings"])
    assert any("No contract found for dataset unknown_dataset" in warning for warning in report["warnings"])
    assert any("missing owner" in failure for failure in report["failed_checks"])
    assert any("missing allowed_roles" in failure for failure in report["failed_checks"])
    assert any("missing encryption key_id" in failure for failure in report["failed_checks"])


def test_load_dataset_records_and_no_sensitive_chunk_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(quality, "_load_parquet_records", lambda path: [{"path": path.name}])
    dataset_paths = {
        "bronze_documents": Path("bronze"),
        "silver_chunks": Path("silver")
    }
    assert quality._load_dataset_records(dataset_paths) == {
        "bronze_documents": [{"path": "bronze"}],
        "silver_chunks": [{"path": "silver"}]
    }

    contracts = Contracts(
        datasets={
            "silver_chunks": _dataset_contract("silver_chunks", "silver", ["document_id"], []),
            "bronze_documents": _dataset_contract("bronze_documents", "bronze", [], []),
            "gold_embeddings": _dataset_contract("gold_embeddings", "gold", [], [])
        },
        roles={},
        classifications={},
        access_policies={},
        lineage=[]
    )
    monkeypatch.setattr(quality, "load_contracts", lambda contracts_dir=None: contracts)
    monkeypatch.setattr(
        quality,
        "_load_dataset_records",
        lambda inner_dataset_paths: {
            "bronze_documents": [],
            "silver_chunks": [{"document_id": "doc-1", "classification": "public"}],
            "gold_embeddings": []
        }
    )
    report = quality.validate_metadata_quality_from_contracts(
        {
            "bronze_documents": Path("bronze"),
            "silver_chunks": Path("silver"),
            "gold_embeddings": Path("gold")
        }
    )
    assert report["checks"]["silver_chunks_confidential_have_allowed_roles"] is True



def test_validate_metadata_quality_wrapper_and_write_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_validate(inner_dataset_paths: dict[str, Path], contracts_dir: Path | None = None) -> dict[str, object]:
        captured["dataset_paths"] = inner_dataset_paths
        captured["contracts_dir"] = contracts_dir
        return {"status": "passed"}

    monkeypatch.setattr(quality, "validate_metadata_quality_from_contracts", fake_validate)

    result = quality.validate_metadata_quality(
        tmp_path / "bronze",
        tmp_path / "silver",
        tmp_path / "gold",
        contracts_dir=tmp_path / "contracts"
    )

    assert result == {"status": "passed"}
    assert captured["dataset_paths"] == {
        "bronze_documents": tmp_path / "bronze",
        "silver_chunks": tmp_path / "silver",
        "gold_embeddings": tmp_path / "gold"
    }

    output_path = tmp_path / "reports" / "quality.json"
    quality.write_quality_report({"status": "passed"}, output_path)
    assert json.loads(output_path.read_text(encoding="utf-8")) == {"status": "passed"}
