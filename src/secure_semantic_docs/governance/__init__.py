"""Governance, permissions, and catalog layer."""

from secure_semantic_docs.governance.audit import (
    get_audit_summary_for_ui,
    load_audit_events,
    log_access_denied_event,
    log_login_event,
    log_search_event,
    write_audit_event
)
from secure_semantic_docs.governance.catalog import export_openmetadata_catalog, generate_openmetadata_assets
from secure_semantic_docs.governance.contracts import (
    get_access_policy,
    get_dataset_contract,
    get_lineage,
    get_role_contract,
    get_safe_fields,
    get_sensitive_fields,
    load_contracts
)
from secure_semantic_docs.governance.permissions import (
    authenticate_user,
    can_access_chunk,
    can_access_record,
    explain_access_decision,
    filter_authorized_records,
    load_users
)
from secure_semantic_docs.governance.quality import validate_metadata_quality, write_quality_report
from secure_semantic_docs.governance.ui_data import (
    get_audit_summary,
    get_authorized_chunk_summary,
    get_governance_summary
)


def __getattr__(name: str):
    """Lazily expose retrieval helpers without creating import cycles."""
    retrieval_exports = {
        "fact_search",
        "insecure_search",
        "load_fact_records",
        "load_gold_records",
        "secure_search"
    }
    if name in retrieval_exports:
        from secure_semantic_docs.governance import retrieval  # noqa: PLC0415
        return getattr(retrieval, name)
    raise AttributeError(name)


__all__ = [
    'authenticate_user',
    'can_access_record',
    'can_access_chunk',
    'explain_access_decision',
    'filter_authorized_records',
    'load_users',
    'write_audit_event',
    'log_search_event',
    'log_login_event',
    'log_access_denied_event',
    'get_audit_summary_for_ui',
    'load_audit_events',
    'fact_search',
    'insecure_search',
    'secure_search',
    'load_fact_records',
    'load_gold_records',
    'generate_openmetadata_assets',
    'export_openmetadata_catalog',
    'load_contracts',
    'get_dataset_contract',
    'get_role_contract',
    'get_access_policy',
    'get_lineage',
    'get_sensitive_fields',
    'get_safe_fields',
    'validate_metadata_quality',
    'write_quality_report',
    'get_authorized_chunk_summary',
    'get_governance_summary',
    'get_audit_summary'
]
