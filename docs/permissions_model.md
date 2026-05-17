# Permissions Model

## Overview

The permissions model enforces role-based access control (RBAC) across all layers
of the platform: ingestion, storage, and retrieval.

Core principle: **Filter first. Decrypt second. Search third. Audit always.**

## Classification Levels

Documents and chunks are classified into four levels:

### public

- Accessible to **all users** (authenticated or not)
- No role or clearance requirement
- Examples: training guides, public announcements, general documentation

### internal

- Accessible to users with **internal clearance or above**
- Requires clearance_level in ["internal", "confidential", "restricted"]
- Examples: engineering runbooks, data quality policies, architectural decisions

### confidential

- Requires **allowed_roles match** + **confidential/restricted clearance**
- Restricted by explicit role list and clearance threshold
- Examples: security audit reports, cryptographic standards, pen test results

### restricted

- Requires **allowed_roles match** + **restricted clearance** + **department match**
- Most stringent: role, clearance, and department must all align
- Examples: payroll policies, budget reports, client contracts

## Clearance Levels

Users have a clearance level that gates access to higher classifications:

- **public**: Access to public records only
- **internal**: Access to public and internal records
- **confidential**: Access to public, internal, and confidential records
- **restricted**: Access to all classification levels (within role/department constraints)

## Pre-Defined Roles

Five roles are pre-defined in the seed data (data/synthetic_data/users/users.json):

### external_viewer

- Clearance: public
- Department: External
- Access: Public records only
- Use case: External partners, consultants, public stakeholders

### business_analyst

- Clearance: internal
- Department: Operations
- Access: Public and internal records
- Use case: Cross-team analysis, business reporting

### data_engineer

- Clearance: internal
- Department: Data Platform
- Access: All lakehouse tables (no classification filtering)
- Use case: Pipeline development, infrastructure

### security_engineer

- Clearance: confidential
- Department: Security
- Access: Public, internal, and confidential security records
- Allowed_roles on: confidential security docs
- Use case: Security audits, compliance, threat analysis

### finance_manager

- Clearance: restricted
- Department: Finance
- Access: Public, internal, and restricted finance records
- Allowed_roles on: restricted finance docs
- Use case: Budget planning, financial forecasting

## Access Rules (Decision Tree)

```
If document has no classification:
    → DENY (fail-safe)

If classification == 'public':
    → ALLOW (for all users)

If classification == 'internal':
    If user.clearance_level in ['internal', 'confidential', 'restricted']:
        → ALLOW
    Else:
        → DENY (insufficient clearance)

If classification == 'confidential':
    If user.role not in document.allowed_roles:
        → DENY (user not in allowed_roles)
    Else if user.clearance_level not in ['confidential', 'restricted']:
        → DENY (insufficient clearance for confidential)
    Else:
        → ALLOW

If classification == 'restricted':
    If user.role not in document.allowed_roles:
        → DENY (user not in allowed_roles)
    Else if user.department != document.department:
        → DENY (user department doesn't match record department)
    Else if user.clearance_level != 'restricted':
        → DENY (insufficient clearance for restricted)
    Else:
        → ALLOW

```

## API Usage

### Loading Users

```python
from secure_semantic_docs.governance import load_users

users = load_users("path/to/users.json")
# {
#     "USR-001": {"user_id": "USR-001", "name": "Alice", ...},
#     "USR-002": {"user_id": "USR-002", "name": "Bob", ...},
#     ...
# }
```

### Checking Access

```python
from secure_semantic_docs.governance import can_access_record

user = users["USR-001"]
document = {
    "classification": "confidential",
    "allowed_roles": ["security_engineer"],
    ...
}

can_access = can_access_record(user, document)  # True or False
```

### Explaining Access Decisions

```python
from secure_semantic_docs.governance import explain_access_decision

decision = explain_access_decision(user, document)
# {
#     "granted": False,
#     "reason": "User role data_engineer not in allowed_roles: ['security_engineer']",
#     "classification": "confidential",
#     "required_roles": ["security_engineer"],
#     "user_role": "data_engineer",
#     "user_clearance": "internal",
#     "user_dept": "Data Platform",
#     "record_dept": "Security",
# }
```

### Filtering Record Lists

```python
from secure_semantic_docs.governance import filter_authorized_records

records = [...]  # List of documents or chunks
authorized = filter_authorized_records(user, records)
```

## Unauthenticated Access

Users can be `None` (unauthenticated). In this case:

```python
can_access_record(None, record)  # Only True if classification == 'public'
```

## Chunks Inherit Permissions

Chunks inherit classification, allowed_roles, and department from their parent documents:

```python
chunk = {
    "chunk_id": "DOC-008-1",
    "document_id": "DOC-008",
    "classification": "confidential",  # Inherited
    "allowed_roles": ["security_engineer"],  # Inherited
    "owner": "Security",
    "department": "Security",  # Inherited
}

can_access_chunk(user, chunk)  # Same logic as can_access_record
```

## Testing Access Decisions

See `tests/unit/governance/test_permissions.py` for comprehensive test coverage:

- Public accessible to all
- Internal requires clearance
- Confidential requires role + clearance
- Restricted requires role + clearance + department
- Access decisions are explained
- Records are filtered correctly

## Future Enterprise Extension

In a production system, this Python-based RBAC would be replaced by:

- **Apache Ranger**: Centralized policy management across Trino, Spark, Hadoop
- **OAuth 2.0**: External authentication (LDAP, SAML, OIDC)
- **ABAC**: Attribute-based access control with fine-grained policies
- **Policy-as-Code**: Infrastructure-as-code for access policies

For this demo, Python RBAC provides sufficient protection and full visibility into
access decisions for learning and audit purposes.
