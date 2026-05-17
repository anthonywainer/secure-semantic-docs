"""Tests for the contract loader."""

from pathlib import Path

import pytest
import yaml

from secure_semantic_docs.governance.contracts import (
    DatasetContract,
    RoleContract,
    get_access_policy,
    get_dataset_contract,
    get_lineage,
    get_role_contract,
    get_safe_fields,
    get_sensitive_fields,
    load_contracts
)


@pytest.fixture
def contracts_dir(tmp_path: Path) -> Path:
    """Create a minimal contracts directory for testing."""
    security_dir = tmp_path / 'security'
    security_dir.mkdir()
    schemas_dir = tmp_path / 'schemas'
    schemas_dir.mkdir()
    del schemas_dir

    datasets = {
        'datasets': {
            'test_dataset': {
                'id': 'test_dataset',
                'name': 'Test Dataset',
                'layer': 'bronze',
                'owner': 'platform',
                'description': 'A test dataset',
                'classification': 'internal',
                'tags': ['test'],
                'fields': [
                    {'name': 'id', 'type': 'STRING', 'required': True, 'sensitive': False},
                    {
                        'name': 'secret',
                        'type': 'BINARY',
                        'required': False,
                        'sensitive': True,
                        'forbidden_in_safe_views': True
                    }
                ],
                'required_fields': ['id'],
                'sensitive_fields': ['secret'],
                'forbidden_fields': ['secret'],
                'lineage_upstream': [],
                'lineage_downstream': ['downstream_ds'],
                'security_notes': 'Test notes',
                'sensitive_flags': {'has_pii': False}
            }
        }
    }

    lineage = {
        'lineage': [
            {'source': 'test_dataset', 'target': 'downstream_ds', 'type': 'transformation'}
        ]
    }

    roles = {
        'roles': {
            'analyst': {'clearance_level': 'internal', 'description': 'Analyst role'},
            'admin': {'clearance_level': 'restricted', 'description': 'Admin'}
        }
    }

    classifications = {
        'levels': ['public', 'internal', 'confidential', 'restricted'],
        'clearance_order': {'public': 0, 'internal': 1, 'confidential': 2, 'restricted': 3}
    }

    policies = {
        'default_policy': {'unknown_user': 'deny', 'missing_classification': 'deny'},
        'classification_policies': {
            'public': {
                'accessible_to_all': True,
                'required_clearance_levels': [],
                'requires_allowed_role': False,
                'requires_department_match': False
            },
            'internal': {
                'accessible_to_all': False,
                'required_clearance_levels': ['internal', 'confidential', 'restricted'],
                'requires_allowed_role': False,
                'requires_department_match': False
            },
            'confidential': {
                'accessible_to_all': False,
                'required_clearance_levels': ['confidential', 'restricted'],
                'requires_allowed_role': True,
                'requires_department_match': False
            },
            'restricted': {
                'accessible_to_all': False,
                'required_clearance_levels': ['restricted'],
                'requires_allowed_role': True,
                'requires_department_match': True
            }
        }
    }

    (tmp_path / 'datasets.yml').write_text(yaml.dump(datasets), encoding='utf-8')
    (tmp_path / 'lineage.yml').write_text(yaml.dump(lineage), encoding='utf-8')
    (security_dir / 'roles.yml').write_text(yaml.dump(roles), encoding='utf-8')
    (security_dir / 'classifications.yml').write_text(yaml.dump(classifications), encoding='utf-8')
    (security_dir / 'access_policies.yml').write_text(yaml.dump(policies), encoding='utf-8')

    return tmp_path


def test_load_contracts_returns_contracts(contracts_dir: Path) -> None:
    contracts = load_contracts(contracts_dir)
    assert 'test_dataset' in contracts.datasets
    assert 'analyst' in contracts.roles
    assert contracts.lineage != []


def test_dataset_contract_fields(contracts_dir: Path) -> None:
    contract = get_dataset_contract('test_dataset', contracts_dir)
    assert isinstance(contract, DatasetContract)
    assert contract.id == 'test_dataset'
    assert contract.layer == 'bronze'
    assert 'id' in contract.required_fields
    assert 'secret' in contract.sensitive_fields
    assert 'secret' in contract.forbidden_fields


def test_role_contract_loaded(contracts_dir: Path) -> None:
    role = get_role_contract('analyst', contracts_dir)
    assert isinstance(role, RoleContract)
    assert role.clearance_level == 'internal'


def test_unknown_dataset_raises(contracts_dir: Path) -> None:
    with pytest.raises(KeyError, match='no_such_dataset'):
        get_dataset_contract('no_such_dataset', contracts_dir)


def test_unknown_role_raises(contracts_dir: Path) -> None:
    with pytest.raises(KeyError, match='ghost'):
        get_role_contract('ghost', contracts_dir)


def test_get_sensitive_fields(contracts_dir: Path) -> None:
    fields = get_sensitive_fields('test_dataset', contracts_dir)
    assert 'secret' in fields
    assert 'id' not in fields


def test_get_safe_fields(contracts_dir: Path) -> None:
    fields = get_safe_fields('test_dataset', contracts_dir)
    assert 'id' in fields
    assert 'secret' not in fields


def test_get_lineage(contracts_dir: Path) -> None:
    edges = get_lineage(contracts_dir)
    assert any(edge['source'] == 'test_dataset' for edge in edges)


def test_get_access_policy(contracts_dir: Path) -> None:
    policy = get_access_policy(contracts_dir)
    assert 'classification_policies' in policy
    assert 'public' in policy['classification_policies']


def test_access_policy_confidential_requires_role(contracts_dir: Path) -> None:
    policy = get_access_policy(contracts_dir)
    confidential_policy = policy['classification_policies']['confidential']
    assert confidential_policy['requires_allowed_role'] is True


def test_access_policy_restricted_requires_department(contracts_dir: Path) -> None:
    policy = get_access_policy(contracts_dir)
    restricted_policy = policy['classification_policies']['restricted']
    assert restricted_policy['requires_department_match'] is True
