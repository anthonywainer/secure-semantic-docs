from __future__ import annotations

from pathlib import Path

import secure_semantic_docs.governance.ui_data as ui_data


def test_load_parquet_records_handles_no_files_and_read_failure(tmp_path: Path, monkeypatch) -> None:
    missing = tmp_path / "missing"
    assert ui_data._load_parquet_records(missing) == []

    layer = tmp_path / "layer"
    layer.mkdir()
    assert ui_data._load_parquet_records(layer) == []

    file_path = layer / "part.parquet"
    file_path.write_text("placeholder", encoding="utf-8")

    import pandas as pd

    monkeypatch.setattr(pd, "read_parquet", lambda path: (_ for _ in ()).throw(ValueError("broken parquet")))
    assert ui_data._load_parquet_records(layer) == []


def test_sanitize_record_converts_lists_and_skips_bytes() -> None:
    record = {
        "document_id": "DOC-1",
        "allowed_roles": ["admin", 5],
        "payload": b"secret",
        "memory": memoryview(b"ignored")
    }

    result = ui_data._sanitize_record(record)

    assert result == {"document_id": "DOC-1", "allowed_roles": ["admin", "5"]}


def test_get_governance_summary_returns_safe_entity_fields(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        ui_data,
        "generate_openmetadata_assets",
        lambda project_root: {
            "entities": [
                {
                    "id": "gold_embeddings",
                    "name": "Gold Embeddings",
                    "type": "Table",
                    "owner": "platform",
                    "description": "Safe summary",
                    "tags": ["gold"],
                    "classification": "confidential",
                    "lineage": {
                        "upstream": ["silver_chunks"],
                        "downstream": ["secure_retrieval_service"]
                    },
                    "security_notes": "Governed"
                }
            ]
        }
    )

    result = ui_data.get_governance_summary({"user_id": "admin"}, project_root=tmp_path)

    assert result == [
        {
            "id": "gold_embeddings",
            "name": "Gold Embeddings",
            "type": "Table",
            "owner": "platform",
            "description": "Safe summary",
            "tags": ["gold"],
            "classification": "confidential",
            "lineage_upstream": ["silver_chunks"],
            "lineage_downstream": ["secure_retrieval_service"],
            "security_notes": "Governed"
        }
    ]
