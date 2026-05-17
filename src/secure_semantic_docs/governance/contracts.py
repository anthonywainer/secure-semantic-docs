"""Contract loader: single source of truth for metadata, schemas, lineage, and security policies."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from secure_semantic_docs.core.settings import BaseSettings
from secure_semantic_docs.loader.yaml_utils import load_yaml_file

logger = logging.getLogger(BaseSettings.APP_NAME)

_REQUIRED_CONTRACT_FILES = (
    'datasets.yml',
    'lineage.yml',
    'security/roles.yml',
    'security/classifications.yml',
    'security/access_policies.yml'
)


def _default_contracts_dir() -> Path:
    """Return the default project contracts directory."""
    return BaseSettings.config_dir / 'contracts'


@dataclass
class FieldContract:
    """Definition of a single dataset field."""

    name: str
    type: str
    required: bool = False
    sensitive: bool = False
    forbidden_in_safe_views: bool = False
    description: str = ''


@dataclass
class DatasetContract:
    """Complete contract for a dataset: fields, lineage, security."""

    id: str
    name: str
    layer: str
    owner: str
    description: str
    classification: str
    tags: list[str]
    fields: list[FieldContract]
    required_fields: list[str]
    sensitive_fields: list[str]
    forbidden_fields: list[str]
    lineage_upstream: list[str]
    lineage_downstream: list[str]
    security_notes: str
    sensitive_flags: dict[str, Any]


@dataclass
class RoleContract:
    """Security role definition."""

    name: str
    clearance_level: str
    description: str
    capabilities: dict[str, Any]


@dataclass
class Contracts:
    """All loaded contracts: datasets, roles, classifications, policies, lineage."""

    datasets: dict[str, DatasetContract]
    roles: dict[str, RoleContract]
    classifications: dict[str, Any]
    access_policies: dict[str, Any]
    lineage: list[dict[str, str]]


def _required_paths(contracts_dir: Path) -> list[Path]:
    """Return the list of required contract file paths."""
    return [contracts_dir / rel_path for rel_path in _REQUIRED_CONTRACT_FILES]


def _ensure_required_files_exist(contracts_dir: Path) -> None:
    """Raise FileNotFoundError when a required contract file is missing."""
    missing = [str(path) for path in _required_paths(contracts_dir) if not path.exists()]
    if missing:
        joined = ', '.join(missing)
        raise FileNotFoundError(f'Missing required contract file(s): {joined}')


def _load_dataset_contracts(datasets_raw: dict[str, Any]) -> dict[str, DatasetContract]:
    """Parse dataset contracts from raw YAML."""
    datasets: dict[str, DatasetContract] = {}
    for dataset_id, dataset_data in (datasets_raw.get('datasets') or {}).items():
        raw_fields = dataset_data.get('fields') or []
        parsed_fields = [
            FieldContract(
                name=field_data['name'],
                type=field_data.get('type', 'STRING'),
                required=bool(field_data.get('required', False)),
                sensitive=bool(field_data.get('sensitive', False)),
                forbidden_in_safe_views=bool(field_data.get('forbidden_in_safe_views', False)),
                description=field_data.get('description', '')
            )
            for field_data in raw_fields
        ]
        datasets[dataset_id] = DatasetContract(
            id=dataset_id,
            name=dataset_data.get('name', dataset_id),
            layer=dataset_data.get('layer', ''),
            owner=dataset_data.get('owner', ''),
            description=dataset_data.get('description', ''),
            classification=dataset_data.get('classification', 'public'),
            tags=list(dataset_data.get('tags') or []),
            fields=parsed_fields,
            required_fields=list(dataset_data.get('required_fields') or []),
            sensitive_fields=list(dataset_data.get('sensitive_fields') or []),
            forbidden_fields=list(dataset_data.get('forbidden_fields') or []),
            lineage_upstream=list(dataset_data.get('lineage_upstream') or []),
            lineage_downstream=list(dataset_data.get('lineage_downstream') or []),
            security_notes=dataset_data.get('security_notes', ''),
            sensitive_flags=dict(dataset_data.get('sensitive_flags') or {})
        )
    return datasets


def _load_role_contracts(roles_raw: dict[str, Any]) -> dict[str, RoleContract]:
    """Parse role contracts from raw YAML."""
    roles: dict[str, RoleContract] = {}
    for role_name, role_data in (roles_raw.get('roles') or {}).items():
        roles[role_name] = RoleContract(
            name=role_name,
            clearance_level=role_data.get('clearance_level', 'public'),
            description=role_data.get('description', ''),
            capabilities=dict(role_data.get('capabilities') or {})
        )
    return roles


def _load_contracts_dir(contracts_dir: Path) -> Contracts:
    """Load all contract files from a contracts directory."""
    _ensure_required_files_exist(contracts_dir)

    datasets_raw = load_yaml_file(contracts_dir / 'datasets.yml')
    lineage_raw = load_yaml_file(contracts_dir / 'lineage.yml')
    roles_raw = load_yaml_file(contracts_dir / 'security' / 'roles.yml')
    classifications_raw = load_yaml_file(contracts_dir / 'security' / 'classifications.yml')
    policies_raw = load_yaml_file(contracts_dir / 'security' / 'access_policies.yml')

    return Contracts(
        datasets=_load_dataset_contracts(datasets_raw),
        roles=_load_role_contracts(roles_raw),
        classifications=classifications_raw,
        access_policies=policies_raw,
        lineage=list(lineage_raw.get('lineage') or [])
    )


def load_contracts(contracts_dir: Path | str | None = None) -> Contracts:
    """Load all contracts from the contracts directory.

    Parameters
    ----------
    contracts_dir
        Path to the contracts directory. Defaults to ``<project_root>/config/contracts``.

    Returns
    -------
    Contracts
        Loaded contracts object.
    """
    resolved = Path(contracts_dir) if contracts_dir else _default_contracts_dir()
    logger.debug('Loading contracts from %s', resolved)
    return _load_contracts_dir(resolved)


def _lookup_contract(
        lookup_fn: Callable[[Contracts], dict[str, Any]],
        item_name: str,
        item_type: str,
        contracts_dir: Path | str | None = None
) -> Any:
    """Return a named contract item or raise KeyError."""
    items = lookup_fn(load_contracts(contracts_dir))
    if item_name not in items:
        raise KeyError(f'No contract defined for {item_type}: {item_name!r}')
    return items[item_name]


def get_dataset_contract(
        dataset_name: str,
        contracts_dir: Path | str | None = None
) -> DatasetContract:
    """Return the contract for a named dataset.

    Parameters
    ----------
    dataset_name
        Dataset identifier, e.g. ``"gold_embeddings"``.
    contracts_dir
        Override for contracts directory.

    Raises
    ------
    KeyError
        When the dataset is not defined in contracts.
    """
    return _lookup_contract(lambda contracts: contracts.datasets, dataset_name, 'dataset', contracts_dir)


def get_role_contract(
        role_name: str,
        contracts_dir: Path | str | None = None
) -> RoleContract:
    """Return the contract for a named role.

    Raises
    ------
    KeyError
        When the role is not defined in contracts.
    """
    return _lookup_contract(lambda contracts: contracts.roles, role_name, 'role', contracts_dir)


def get_access_policy(contracts_dir: Path | str | None = None) -> dict[str, Any]:
    """Return the loaded access policies dict."""
    return load_contracts(contracts_dir).access_policies


def get_lineage(contracts_dir: Path | str | None = None) -> list[dict[str, str]]:
    """Return the list of lineage edge dicts (source, target, type)."""
    return load_contracts(contracts_dir).lineage


def get_sensitive_fields(
        dataset_name: str,
        contracts_dir: Path | str | None = None
) -> list[str]:
    """Return the list of sensitive field names for a dataset.

    Sensitive fields must not appear in UI output or safe views.
    """
    contract = get_dataset_contract(dataset_name, contracts_dir)
    return list(contract.sensitive_fields)


def get_safe_fields(
        dataset_name: str,
        contracts_dir: Path | str | None = None
) -> list[str]:
    """Return fields that are safe to expose (non-sensitive, non-forbidden)."""
    contract = get_dataset_contract(dataset_name, contracts_dir)
    forbidden = set(contract.forbidden_fields)
    sensitive = set(contract.sensitive_fields)
    return [
        field.name
        for field in contract.fields
        if field.name not in forbidden
           and field.name not in sensitive
           and not field.forbidden_in_safe_views
           and not field.sensitive
    ]
