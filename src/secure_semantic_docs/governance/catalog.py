"""Governance and catalog export for OpenMetadata compatibility."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from secure_semantic_docs.core.settings import BaseSettings
from secure_semantic_docs.governance.contracts import load_contracts

logger = logging.getLogger(BaseSettings.APP_NAME)

_ENTITY_TYPE_MAP: dict[str, str] = {
    'landing': 'Table',
    'bronze': 'Table',
    'silver': 'Table',
    'gold': 'Table',
    'serving': 'Database',
    'ui': 'Application',
    'audit': 'Log'
}


def _dataset_to_entity(dataset: Any, lineage_edges: list[dict[str, str]]) -> dict[str, Any]:
    """Convert a DatasetContract to an OpenMetadata entity dict."""
    upstream = [edge['source'] for edge in lineage_edges if edge['target'] == dataset.id]
    downstream = [edge['target'] for edge in lineage_edges if edge['source'] == dataset.id]

    entity_type = _ENTITY_TYPE_MAP.get(dataset.layer, 'Table')
    if dataset.id == 'secure_retrieval_service':
        entity_type = 'API'
    elif dataset.id == 'audit_events':
        entity_type = 'Log'

    fields = [
        {
            'name': field.name,
            'type': field.type,
            'description': field.description
        }
        for field in dataset.fields
    ]

    return {
        'id': dataset.id,
        'name': dataset.name,
        'type': entity_type,
        'layer': dataset.layer,
        'owner': dataset.owner,
        'description': dataset.description,
        'tags': dataset.tags,
        'classification': dataset.classification,
        'fields': fields,
        'lineage': {'upstream': upstream, 'downstream': downstream},
        'security_notes': dataset.security_notes,
        'sensitive_flags': dataset.sensitive_flags
    }


def generate_openmetadata_assets(
        project_root: Path | str,
        contracts_dir: Path | str | None = None
) -> dict[str, Any]:
    """Generate an OpenMetadata-compatible asset catalog from contracts.

    Parameters
    ----------
    project_root
        Project root directory.
    contracts_dir
        Override for contracts directory. Defaults to ``<project_root>/config/contracts``.
    """
    now = datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    resolved_project_root = Path(project_root).resolve()
    resolved_contracts = (
        Path(contracts_dir)
        if contracts_dir
        else resolved_project_root / 'config' / 'contracts'
    )

    contracts = load_contracts(resolved_contracts)
    lineage_edges = contracts.lineage
    entities = [
        _dataset_to_entity(dataset_contract, lineage_edges)
        for dataset_contract in contracts.datasets.values()
    ]
    roles = [role.name for role in contracts.roles.values()]
    clearance_order = contracts.classifications.get('clearance_order', {})

    return {
        'catalog_name': 'secure-semantic-docs',
        'version': '1.0',
        'generated_at': now,
        'project_root': str(resolved_project_root),
        'entities': entities,
        'lineage_graph': {
            'nodes': [entity['id'] for entity in entities],
            'edges': lineage_edges
        },
        'security_model': {
            'classifications': contracts.classifications.get('levels', []),
            'roles': roles,
            'clearance_order': clearance_order,
            'encryption_algorithm': 'XSalsa20-Poly1305',
            'key_management': 'local-dev-only',
            'direct_sql_access': 'governed_views_only',
            'direct_sql_note': (
                'Trino and Superset expose only safe.* governed views. '
                'Raw schema access remains admin-only, while semantic retrieval '
                'stays in the controlled Streamlit application.'
            )
        }
    }


def export_openmetadata_catalog(
        output_path: Path | str,
        project_root: Path | str = '.',
        contracts_dir: Path | str | None = None
) -> None:
    """Export the OpenMetadata-compatible catalog to JSON.

    Parameters
    ----------
    output_path
        Destination JSON file path.
    project_root
        Project root directory.
    contracts_dir
        Override for contracts directory.
    """
    catalog = generate_openmetadata_assets(project_root, contracts_dir)
    resolved_output_path = Path(output_path)
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)

    with resolved_output_path.open('w', encoding='utf-8') as output_file:
        json.dump(catalog, output_file, indent=2)

    logger.info('Exported OpenMetadata catalog to %s', resolved_output_path)
