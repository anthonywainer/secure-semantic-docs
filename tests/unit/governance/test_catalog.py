from __future__ import annotations

import json
from pathlib import Path

import pytest

import secure_semantic_docs.governance.catalog as catalog
from secure_semantic_docs.governance.contracts import (
    Contracts,
    DatasetContract,
    FieldContract,
    RoleContract
)


def _dataset(dataset_id: str, layer: str, name: str = "Dataset") -> DatasetContract:
    return DatasetContract(
        id=dataset_id,
        name=name,
        layer=layer,
        owner="platform",
        description=f"Description for {dataset_id}",
        classification="internal",
        tags=["governed"],
        fields=[FieldContract(name="document_id", type="STRING", description="Doc ID")],
        required_fields=["document_id"],
        sensitive_fields=[],
        forbidden_fields=[],
        lineage_upstream=[],
        lineage_downstream=[],
        security_notes="Use governed access",
        sensitive_flags={"has_pii": False}
    )


def _contracts() -> Contracts:
    return Contracts(
        datasets={
            "bronze_documents": _dataset("bronze_documents", "bronze", name="Bronze"),
            "secure_retrieval_service": _dataset(
                "secure_retrieval_service",
                "serving",
                name="Retrieval Service"
            ),
            "audit_events": _dataset("audit_events", "audit", name="Audit Events")
        },
        roles={
            "admin": RoleContract(
                name="admin",
                clearance_level="restricted",
                description="Administrator",
                capabilities={"can_access_all_records": True}
            )
        },
        classifications={
            "levels": ["public", "internal"],
            "clearance_order": {"public": 0, "internal": 1}
        },
        access_policies={"classification_policies": {}},
        lineage=[
            {"source": "bronze_documents", "target": "secure_retrieval_service"},
            {"source": "secure_retrieval_service", "target": "audit_events"}
        ]
    )


def test_dataset_to_entity_maps_special_types_and_lineage() -> None:
    service = _dataset("secure_retrieval_service", "serving", name="Retrieval Service")
    audit = _dataset("audit_events", "audit", name="Audit Events")

    service_entity = catalog._dataset_to_entity(service, _contracts().lineage)
    audit_entity = catalog._dataset_to_entity(audit, _contracts().lineage)

    assert service_entity["type"] == "API"
    assert service_entity["fields"] == [
        {"name": "document_id", "type": "STRING", "description": "Doc ID"}
    ]
    assert service_entity["lineage"] == {
        "upstream": ["bronze_documents"],
        "downstream": ["audit_events"]
    }
    assert audit_entity["type"] == "Log"


def test_generate_openmetadata_assets_uses_default_contract_path(tmp_path: Path) -> None:
    captured: dict[str, Path] = {}

    def fake_load_contracts(path: Path) -> Contracts:
        captured["path"] = path
        return _contracts()

    original_loader = catalog.load_contracts
    catalog.load_contracts = fake_load_contracts
    try:
        assets = catalog.generate_openmetadata_assets(tmp_path)
    finally:
        catalog.load_contracts = original_loader

    assert captured["path"] == tmp_path.resolve() / "config" / "contracts"
    assert assets["catalog_name"] == "secure-semantic-docs"
    assert assets["project_root"] == str(tmp_path.resolve())
    assert assets["lineage_graph"]["edges"] == _contracts().lineage
    assert assets["security_model"]["roles"] == ["admin"]
    assert assets["security_model"]["clearance_order"] == {"public": 0, "internal": 1}


def test_export_openmetadata_catalog_writes_json(tmp_path: Path) -> None:
    output_path = tmp_path / "nested" / "catalog.json"
    payload = {"catalog_name": "demo", "entities": []}

    original_generator = catalog.generate_openmetadata_assets
    catalog.generate_openmetadata_assets = lambda project_root, contracts_dir=None: payload
    try:
        catalog.export_openmetadata_catalog(output_path, project_root=tmp_path)
    finally:
        catalog.generate_openmetadata_assets = original_generator

    assert output_path.exists()
    assert json.loads(output_path.read_text(encoding="utf-8")) == payload


def test_ensure_required_files_exist_raises_for_missing_files(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="datasets.yml"):
        catalog.load_contracts(tmp_path)
