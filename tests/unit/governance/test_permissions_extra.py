from __future__ import annotations

import json
from pathlib import Path

import pytest

import secure_semantic_docs.governance.permissions as permissions
from secure_semantic_docs.governance.contracts import RoleContract


def test_normalized_allowed_roles_handles_non_iterable(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    class _NonIterable:
        pass

    sentinel = object()

    def fake_list(value):
        if value is sentinel:
            return _NonIterable()
        if isinstance(value, _NonIterable):
            raise TypeError("not iterable")
        return []

    monkeypatch.setattr(permissions, "list", fake_list, raising=False)
    assert permissions._normalized_allowed_roles({"allowed_roles": sentinel}) == []


def test_can_access_all_records_honors_direct_flag() -> None:
    assert permissions._can_access_all_records({"can_access_all_records": True}) is True


def test_can_access_all_records_returns_false_when_role_missing() -> None:
    assert permissions._can_access_all_records({"role": ""}) is False


def test_can_access_all_records_returns_false_on_role_lookup_errors(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(permissions, "get_role_contract", lambda role, contracts_dir=None: (_ for _ in ()).throw(KeyError(role)))
    assert permissions._can_access_all_records({"role": "ghost"}) is False


def test_can_access_all_records_uses_role_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        permissions,
        "get_role_contract",
        lambda role, contracts_dir=None: RoleContract(
            name=role,
            clearance_level="restricted",
            description="admin",
            capabilities={"can_access_all_records": True}
        )
    )
    assert permissions._can_access_all_records({"role": "admin"}) is True


def test_load_users_handles_missing_file_and_reads_json(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert permissions.load_users(missing) == {}

    users_path = tmp_path / "users.json"
    users_path.write_text(
        json.dumps([
            {"user_id": "alice", "password": "secret"},
            {"user_id": "bob", "password": "hunter2"}
        ]),
        encoding="utf-8"
    )

    loaded = permissions.load_users(users_path)
    assert loaded["alice"]["password"] == "secret"
    assert loaded["bob"]["user_id"] == "bob"


def test_can_access_record_denies_missing_classification() -> None:
    user = {"role": "admin", "clearance_level": "restricted"}
    assert permissions.can_access_record(user, {"allowed_roles": []}) is False


def test_can_access_record_denies_unknown_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(permissions, "_load_classification_policy", lambda contracts_dir=None: lambda classification: None)
    user = {"role": "admin", "clearance_level": "restricted"}
    record = {"classification": "unknown", "allowed_roles": []}
    assert permissions.can_access_record(user, record) is False


def test_explain_access_decision_for_unauthenticated_user() -> None:
    record = {"classification": "public", "allowed_roles": [], "department": "Ops"}
    decision = permissions.explain_access_decision(None, record)
    assert decision["granted"] is True
    assert decision["reason"] == "Unauthenticated user; public records only"
    assert decision["user_role"] == "none"


def test_explain_access_decision_for_unknown_classification(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(permissions, "_load_classification_policy", lambda contracts_dir=None: lambda classification: None)
    user = {"role": "admin", "clearance_level": "restricted", "department": "Ops"}
    record = {"classification": "mystery", "allowed_roles": [], "department": "Ops"}

    decision = permissions.explain_access_decision(user, record)

    assert decision["reason"] == "Unknown classification: mystery"
    assert decision["granted"] is False


def test_explain_access_decision_for_department_mismatch(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        permissions,
        "_load_classification_policy",
        lambda contracts_dir=None: lambda classification: {
            "accessible_to_all": False,
            "required_clearance_levels": ["restricted"],
            "requires_allowed_role": True,
            "requires_department_match": True
        }
    )
    monkeypatch.setattr(permissions, "_can_access_all_records", lambda current_user, contracts_dir=None: False)

    user = {
        "role": "finance_manager",
        "clearance_level": "restricted",
        "department": "Security"
    }
    record = {
        "classification": "restricted",
        "allowed_roles": ["finance_manager"],
        "department": "Finance"
    }

    decision = permissions.explain_access_decision(user, record)

    assert "User department Security != record department Finance" == decision["reason"]
    assert decision["granted"] is False


def test_explain_access_decision_for_successful_access(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        permissions,
        "_load_classification_policy",
        lambda contracts_dir=None: lambda classification: {
            "accessible_to_all": False,
            "required_clearance_levels": ["restricted"],
            "requires_allowed_role": True,
            "requires_department_match": False
        }
    )
    monkeypatch.setattr(permissions, "_can_access_all_records", lambda current_user, contracts_dir=None: False)

    user = {
        "role": "finance_manager",
        "clearance_level": "restricted",
        "department": "Finance"
    }
    record = {
        "classification": "restricted",
        "allowed_roles": ["finance_manager"],
        "department": "Finance"
    }

    decision = permissions.explain_access_decision(user, record)

    assert decision["granted"] is True
    assert decision["reason"] == "User has required clearance and role for restricted"



def test_explain_access_decision_for_insufficient_clearance(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        permissions,
        "_load_classification_policy",
        lambda contracts_dir=None: lambda classification: {
            "accessible_to_all": False,
            "required_clearance_levels": ["restricted"],
            "requires_allowed_role": False,
            "requires_department_match": False
        }
    )
    monkeypatch.setattr(permissions, "_can_access_all_records", lambda current_user, contracts_dir=None: False)

    user = {"role": "analyst", "clearance_level": "internal", "department": "Ops"}
    record = {"classification": "restricted", "allowed_roles": [], "department": "Ops"}

    decision = permissions.explain_access_decision(user, record)

    assert decision["granted"] is False
    assert decision["reason"] == "Insufficient clearance: internal not in ['restricted']"
