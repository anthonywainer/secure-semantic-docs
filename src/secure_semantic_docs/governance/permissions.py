"""Role-based access control and permission enforcement.

Access rules are driven by contracts/security/access_policies.yml.
The public API is unchanged.
"""

import json
import logging
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from secure_semantic_docs.core.settings import BaseSettings
from secure_semantic_docs.governance.contracts import get_access_policy, get_role_contract

logger = logging.getLogger(BaseSettings.APP_NAME)

ClassificationPolicyLookup = Callable[[str], dict[str, Any] | None]


def _load_classification_policy(
        contracts_dir: Path | str | None = None
) -> ClassificationPolicyLookup:
    """Load classification policies and return a lookup function."""
    policies = get_access_policy(contracts_dir)
    class_policies = dict(policies.get('classification_policies', {}))

    def lookup(classification: str) -> dict[str, Any] | None:
        return class_policies.get(classification)

    return lookup


def _normalized_allowed_roles(record: dict[str, Any]) -> list[str]:
    """Return a normalized allowed_roles list from a record."""
    raw_roles = record.get('allowed_roles') or []
    return list(raw_roles) if isinstance(raw_roles, Iterable) else []


def _get_required_clearance_levels(
        classification: str,
        contracts_dir: Path | str | None = None
) -> set[str]:
    """Return the set of clearance levels that satisfy a classification policy."""
    policy_lookup = _load_classification_policy(contracts_dir)
    policy = policy_lookup(classification) or {}
    return set(policy.get('required_clearance_levels', []))


def _can_access_all_records(
        user: dict[str, Any],
        contracts_dir: Path | str | None = None
) -> bool:
    """Return true when the user's role grants governed all-record access."""
    if bool(user.get('can_access_all_records')):
        return True

    role_name = str(user.get('role', ''))
    if not role_name:
        return False

    try:
        role_contract = get_role_contract(role_name, contracts_dir)
    except (FileNotFoundError, KeyError):
        return False

    return bool(role_contract.capabilities.get('can_access_all_records'))


def load_users(users_path: Path | str) -> dict[str, dict]:
    """Load users from JSON file.

    Parameters
    ----------
    users_path
        Path to users.json file.

    Returns
    -------
    dict
        Mapping of user_id to user record.
    """
    users_path = Path(users_path)
    if not users_path.exists():
        logger.warning('Users file not found: %s', users_path)
        return {}

    with users_path.open(encoding='utf-8') as file_handle:
        users_list = json.load(file_handle)

    return {user['user_id']: user for user in users_list}


def can_access_record(
        user: dict | None,
        record: dict,
        contracts_dir: Path | str | None = None
) -> bool:
    """Check if a user can access a record based on classification and roles.

    Access rules are loaded from contracts/security/access_policies.yml.
    Default policy: unknown user → deny; missing classification → deny.

    Parameters
    ----------
    user
        User record with role, department, clearance_level. None = unauthenticated.
    record
        Document or chunk record with classification, allowed_roles, department.
    contracts_dir
        Override for contracts directory (used in tests).

    Returns
    -------
    bool
        True if user can access the record.
    """
    classification_value = record.get('classification')
    if user is None:
        return classification_value == 'public'

    if not classification_value:
        return False

    classification = str(classification_value)
    policy_lookup = _load_classification_policy(contracts_dir)
    policy = policy_lookup(classification)
    if policy is None:
        logger.warning('No policy for classification %r — denying by default', classification)
        return False

    if policy.get('accessible_to_all'):
        return True

    if _can_access_all_records(user, contracts_dir):
        return True

    allowed_roles = _normalized_allowed_roles(record)
    user_role = user.get('role', 'unknown')
    user_clearance = user.get('clearance_level', 'public')
    user_department = user.get('department')
    record_department = record.get('department')

    required_clearance = _get_required_clearance_levels(classification, contracts_dir)
    if required_clearance and user_clearance not in required_clearance:
        return False

    if policy.get('requires_allowed_role') and user_role not in allowed_roles:
        return False

    if policy.get('requires_department_match') and user_department != record_department:
        return False

    return True


def can_access_chunk(
        user: dict | None,
        chunk: dict,
        contracts_dir: Path | str | None = None
) -> bool:
    """Check if a user can access a chunk record.

    Chunks inherit classification, allowed_roles, and owner from the document.

    Parameters
    ----------
    user
        User record.
    chunk
        Chunk record with classification, allowed_roles, owner, department.
    contracts_dir
        Override for contracts directory (used in tests).

    Returns
    -------
    bool
        True if user can access the chunk.
    """
    return can_access_record(user, chunk, contracts_dir)


def explain_access_decision(
        user: dict | None,
        record: dict,
        contracts_dir: Path | str | None = None
) -> dict[str, Any]:
    """Explain why access was granted or denied.

    Parameters
    ----------
    user
        User record.
    record
        Document or chunk record.
    contracts_dir
        Override for contracts directory (used in tests).

    Returns
    -------
    dict
        Explanation with granted, reason, classification, required_roles,
        user_role, user_clearance, user_dept, record_dept.
    """
    granted = can_access_record(user, record, contracts_dir)
    classification = str(record.get('classification', 'unknown') or 'unknown')
    allowed_roles = _normalized_allowed_roles(record)
    user_role = user.get('role', 'unknown') if user else 'none'
    user_clearance = user.get('clearance_level', 'none') if user else 'none'
    user_department = user.get('department', 'none') if user else 'none'
    record_department = record.get('department', 'none')

    if not user:
        return {
            'granted': granted,
            'reason': 'Unauthenticated user; public records only',
            'classification': classification,
            'required_roles': allowed_roles,
            'user_role': 'none',
            'user_clearance': 'none',
            'user_dept': 'none',
            'record_dept': record_department
        }

    policy_lookup = _load_classification_policy(contracts_dir)
    policy = policy_lookup(classification)
    if classification == 'public' and policy and policy.get('accessible_to_all'):
        reason = 'Public record; accessible to everyone'
    elif policy is None:
        reason = f'Unknown classification: {classification}'
    else:
        required_clearance = set(policy.get('required_clearance_levels', []))
        requires_role = policy.get('requires_allowed_role', False)
        requires_department = policy.get('requires_department_match', False)

        if requires_role and user_role not in allowed_roles:
            reason = f'User role {user_role} not in allowed_roles: {allowed_roles}'
        elif requires_department and user_department != record_department:
            reason = (
                f'User department {user_department} '
                f'!= record department {record_department}'
            )
        elif required_clearance and user_clearance not in required_clearance:
            reason = (
                f'Insufficient clearance: {user_clearance} '
                f'not in {sorted(required_clearance)}'
            )
        else:
            reason = f'User has required clearance and role for {classification}'

    return {
        'granted': granted,
        'reason': reason,
        'classification': classification,
        'required_roles': allowed_roles,
        'user_role': user_role,
        'user_clearance': user_clearance,
        'user_dept': user_department,
        'record_dept': record_department
    }


def filter_authorized_records(
        user: dict | None,
        records: list[dict],
        contracts_dir: Path | str | None = None
) -> list[dict]:
    """Filter records to only those a user can access.

    Parameters
    ----------
    user
        User record.
    records
        List of document or chunk records.
    contracts_dir
        Override for contracts directory (used in tests).

    Returns
    -------
    list[dict]
        Filtered records that the user can access.
    """
    return [record for record in records if can_access_record(user, record, contracts_dir)]


def authenticate_user(
        user_id: str,
        password: str,
        users: dict[str, dict]
) -> dict | None:
    """Authenticate a demo user by user_id and plain-text password.

    .. warning::
        This is **demo-only** authentication using plain-text password comparison.
        It is not suitable for production use.

    Parameters
    ----------
    user_id
        The user identifier to look up.
    password
        Plain-text password to compare against the stored value.
    users
        Mapping of user_id to user record, as returned by :func:`load_users`.

    Returns
    -------
    dict | None
        The user record if authentication succeeds, ``None`` otherwise.
    """
    user = users.get(user_id)
    if not user:
        logger.warning('Authentication failed: unknown user_id=%s', user_id)
        return None

    stored_password = user.get('password', '')
    if password != stored_password:
        logger.warning('Authentication failed: wrong password for user_id=%s', user_id)
        return None

    return user
