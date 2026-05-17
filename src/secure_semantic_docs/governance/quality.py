"""Metadata quality checks and validation."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from secure_semantic_docs.core.settings import BaseSettings
from secure_semantic_docs.governance.contracts import DatasetContract, load_contracts

logger = logging.getLogger(BaseSettings.APP_NAME)

_LEGACY_REQUIRED_CHECK_NAMES: dict[tuple[str, str], str] = {
    ('bronze_documents', 'classification'): 'bronze_documents_have_classification',
    ('bronze_documents', 'owner'): 'bronze_documents_have_owner',
    ('bronze_documents', 'allowed_roles'): 'bronze_documents_have_allowed_roles',
    ('silver_chunks', 'document_id'): 'silver_chunks_have_document_id',
    ('silver_chunks', 'classification'): 'silver_chunks_have_classification',
    ('gold_embeddings', 'chunk_id'): 'gold_embeddings_link_to_chunk',
    ('gold_embeddings', 'document_id'): 'gold_embeddings_link_to_document',
    ('gold_embeddings', 'classification'): 'gold_embeddings_have_classification'
}


def _load_parquet_records(layer_path: Path) -> list[dict]:
    """Load Parquet records from a lakehouse layer directory."""
    if not layer_path.exists():
        return []
    try:
        import pandas as pd
        parquet_files = list(layer_path.rglob('*.parquet'))
        if not parquet_files:
            return []
        df = pd.concat([pd.read_parquet(f) for f in parquet_files], ignore_index=True)
        return df.to_dict('records')
    except Exception as exc:
        logger.warning('Could not load Parquet from %s: %s', layer_path, exc)
        return []


def _is_empty_value(value: object) -> bool:
    """Return True if value is considered empty (None, empty string, empty sequence)."""
    if value is None:
        return True
    try:
        import numpy as np
    except ImportError:
        np = None
    if np is not None and isinstance(value, np.ndarray):
        return len(value) == 0
    return value in ('', [], ())


def _count_non_null(records: list[dict], field: str) -> tuple[int, int]:
    """Return (total, count_with_non_null_value) for a field across records."""
    total = len(records)
    with_value = sum(1 for record in records if not _is_empty_value(record.get(field)))
    return total, with_value


def _required_check_name(dataset_id: str, field_name: str) -> str:
    """Return the check name for a required field."""
    return _LEGACY_REQUIRED_CHECK_NAMES.get(
        (dataset_id, field_name),
        f'{dataset_id}_have_{field_name}'
    )


def _run_check(
        checks: dict[str, bool],
        failed_checks: list[str],
        records: list[dict],
        check_name: str,
        field: str,
        failure_msg: str
) -> None:
    """Run a non-null check for a field and record result."""
    if not records:
        return
    total, with_value = _count_non_null(records, field)
    checks[check_name] = with_value == total
    if with_value < total:
        failed_checks.append(failure_msg.format(missing=total - with_value, total=total))


def _check_required_fields(
        checks: dict[str, bool],
        failed_checks: list[str],
        records: list[dict],
        dataset_id: str,
        required_fields: list[str]
) -> None:
    """Check that all required fields are non-null for a dataset's records."""
    for field_name in required_fields:
        check_name = _required_check_name(dataset_id, field_name)
        _run_check(
            checks,
            failed_checks,
            records,
            check_name,
            field_name,
            f'{dataset_id}: {{missing}}/{{total}} missing {field_name}'
        )


def _check_no_forbidden_fields(
        checks: dict[str, bool],
        failed_checks: list[str],
        records: list[dict],
        dataset_id: str,
        forbidden_fields: list[str]
) -> None:
    """Check that forbidden fields are not populated in records."""
    for field_name in forbidden_fields:
        check_name = f'{dataset_id}_no_{field_name}'
        if not records:
            checks[check_name] = True
            continue
        exposed = sum(1 for record in records if not _is_empty_value(record.get(field_name)))
        checks[check_name] = exposed == 0
        if exposed > 0:
            failed_checks.append(
                f'{dataset_id}: {exposed}/{len(records)} records expose forbidden field {field_name!r}'
            )


def _dataset_paths(
        bronze_path: Path | str,
        silver_path: Path | str,
        gold_path: Path | str
) -> dict[str, Path]:
    """Return dataset ids mapped to resolved lakehouse paths."""
    return {
        'bronze_documents': Path(bronze_path),
        'silver_chunks': Path(silver_path),
        'gold_embeddings': Path(gold_path)
    }


def _load_dataset_records(dataset_paths: dict[str, Path]) -> dict[str, list[dict]]:
    """Load records for each dataset path."""
    return {
        dataset_id: _load_parquet_records(dataset_path)
        for dataset_id, dataset_path in dataset_paths.items()
    }


def _append_missing_data_warnings(
        warnings: list[str],
        dataset_paths: dict[str, Path],
        dataset_records: dict[str, list[dict]]
) -> None:
    """Append warnings for datasets that have no loaded records."""
    for dataset_id, dataset_path in dataset_paths.items():
        if dataset_records.get(dataset_id):
            continue
        label = dataset_id.split('_')[0]
        warnings.append(f'No {label} records found at {dataset_path}')


def _is_safe_view_dataset(dataset: DatasetContract) -> bool:
    """Return True when a dataset represents a safe serving surface."""
    return dataset.layer in {'serving', 'ui'}


def validate_metadata_quality_from_contracts(
        dataset_paths: dict[str, Path | str],
        contracts_dir: Path | str | None = None
) -> dict[str, Any]:
    """Validate dataset quality using required field rules from contracts.

    Parameters
    ----------
    dataset_paths
        Mapping of dataset id to Parquet directory path.
    contracts_dir
        Override for contracts directory.

    Returns
    -------
    dict
        Quality report with checks, passed, failed, and warnings.
    """
    resolved_paths = {
        dataset_id: Path(dataset_path)
        for dataset_id, dataset_path in dataset_paths.items()
    }
    contracts = load_contracts(contracts_dir)
    checks: dict[str, bool] = {}
    warnings: list[str] = []
    failed_checks: list[str] = []
    dataset_records = _load_dataset_records(resolved_paths)

    _append_missing_data_warnings(warnings, resolved_paths, dataset_records)

    for dataset_id in resolved_paths:
        dataset_contract = contracts.datasets.get(dataset_id)
        if dataset_contract is None:
            warnings.append(f'No contract found for dataset {dataset_id}')
            continue

        records = dataset_records.get(dataset_id, [])
        _check_required_fields(
            checks,
            failed_checks,
            records,
            dataset_id,
            dataset_contract.required_fields
        )

        if dataset_id == 'silver_chunks':
            sensitive_chunks = [
                record
                for record in records
                if record.get('classification') in ('confidential', 'restricted')
            ]
            if sensitive_chunks:
                total, with_roles = _count_non_null(sensitive_chunks, 'allowed_roles')
                checks['silver_chunks_confidential_have_allowed_roles'] = with_roles == total
                if with_roles < total:
                    failed_checks.append(
                        f'silver_chunks confidential: {total - with_roles}/{total} missing allowed_roles'
                    )
            else:
                checks['silver_chunks_confidential_have_allowed_roles'] = True

        if dataset_id == 'gold_embeddings':
            checks['gold_embeddings_have_encryption_metadata'] = True
            checks['gold_embeddings_no_plaintext_vectors'] = True
            if records:
                total, with_key = _count_non_null(records, 'key_id')
                checks['gold_embeddings_have_encryption_metadata'] = with_key == total
                if with_key < total:
                    failed_checks.append(
                        f'gold_embeddings: {total - with_key}/{total} missing encryption key_id'
                    )

        if _is_safe_view_dataset(dataset_contract):
            _check_no_forbidden_fields(
                checks,
                failed_checks,
                records,
                dataset_id,
                dataset_contract.forbidden_fields
            )

    return {
        'timestamp': datetime.now(UTC).isoformat().replace('+00:00', 'Z'),
        'checks': checks,
        'passed': sum(1 for passed in checks.values() if passed),
        'total': len(checks),
        'failed_checks': failed_checks,
        'warnings': warnings,
        'status': 'passed' if all(checks.values()) else 'failed'
    }


def validate_metadata_quality(
        bronze_path: Path | str,
        silver_path: Path | str,
        gold_path: Path | str,
        contracts_dir: Path | str | None = None
) -> dict[str, Any]:
    """Validate metadata quality across bronze, silver, and gold layers.

    Checks are derived from dataset contracts (required fields and security metadata).

    Parameters
    ----------
    bronze_path
        Path to bronze_documents Parquet directory.
    silver_path
        Path to silver_chunks Parquet directory.
    gold_path
        Path to gold_embeddings Parquet directory.
    contracts_dir
        Override for contracts directory.

    Returns
    -------
    dict
        Quality report with checks, passed, failed, and warnings.
    """
    return validate_metadata_quality_from_contracts(
        _dataset_paths(bronze_path, silver_path, gold_path),
        contracts_dir
    )


def write_quality_report(
        report: dict[str, Any],
        output_path: Path | str = 'runtime/logs/metadata_quality_report.json'
) -> None:
    """Write quality report to JSON file.

    Parameters
    ----------
    report
        Quality report dict.
    output_path
        Output path for report.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open('w', encoding='utf-8') as file_handle:
        json.dump(report, file_handle, indent=2)

    logger.info('Wrote quality report to %s', output_path)
