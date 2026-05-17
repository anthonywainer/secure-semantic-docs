"""Tests for permissions module."""

import pytest

from secure_semantic_docs.governance import (
    can_access_chunk,
    can_access_record,
    explain_access_decision,
    filter_authorized_records,
)


@pytest.fixture
def business_analyst():
    """Business analyst user."""
    return {
        "user_id": "USR-002",
        "name": "Bob Martinez",
        "role": "business_analyst",
        "department": "Operations",
        "clearance_level": "internal"
    }


@pytest.fixture
def security_engineer():
    """Security engineer user."""
    return {
        "user_id": "USR-003",
        "name": "Carol Smith",
        "role": "security_engineer",
        "department": "Security",
        "clearance_level": "confidential"
    }


@pytest.fixture
def external_viewer():
    """External viewer user."""
    return {
        "user_id": "USR-005",
        "name": "Eve Johnson",
        "role": "external_viewer",
        "department": "External",
        "clearance_level": "public"
    }


@pytest.fixture
def public_document():
    """Public document record."""
    return {
        "document_id": "DOC-022",
        "title": "PySpark Best Practices Guide",
        "classification": "public",
        "allowed_roles": [],
        "owner": "Pamela Lopez",
        "department": "Data Platform"
    }


@pytest.fixture
def confidential_document():
    """Confidential document record."""
    return {
        "document_id": "DOC-008",
        "title": "Security Audit Report",
        "classification": "confidential",
        "allowed_roles": ["security_engineer", "compliance_officer"],
        "owner": "Erik Williams",
        "department": "Security"
    }


@pytest.fixture
def restricted_document():
    """Restricted document record."""
    return {
        "document_id": "DOC-010",
        "title": "Payroll Policy",
        "classification": "restricted",
        "allowed_roles": ["finance_manager", "hr_manager"],
        "owner": "Brittney Campbell",
        "department": "Finance"
    }


def test_public_accessible_to_all(public_document, business_analyst, external_viewer):
    """Public documents accessible to everyone."""
    assert can_access_record(None, public_document) is True
    assert can_access_record(business_analyst, public_document) is True
    assert can_access_record(external_viewer, public_document) is True


def test_internal_requires_internal_clearance(confidential_document):
    """Internal documents require internal clearance."""
    internal_doc = {**confidential_document, "classification": "internal"}

    business_analyst = {
        "role": "business_analyst",
        "clearance_level": "internal",
        "department": "Operations",
    }
    assert can_access_record(business_analyst, internal_doc) is True

    external_viewer = {
        "role": "external_viewer",
        "clearance_level": "public",
        "department": "External",
    }
    assert can_access_record(external_viewer, internal_doc) is False


def test_confidential_requires_role(confidential_document, security_engineer, business_analyst):
    """Confidential documents require allowed role."""
    assert can_access_record(security_engineer, confidential_document) is True
    assert can_access_record(business_analyst, confidential_document) is False


def test_restricted_requires_role_and_department(restricted_document):
    """Restricted documents require role AND department match."""
    finance_manager = {
        "role": "finance_manager",
        "clearance_level": "restricted",
        "department": "Finance"
    }
    assert can_access_record(finance_manager, restricted_document) is True

    wrong_department = {
        "role": "finance_manager",
        "clearance_level": "restricted",
        "department": "Security"
    }
    assert can_access_record(wrong_department, restricted_document) is False

    wrong_role = {
        "role": "security_engineer",
        "clearance_level": "restricted",
        "department": "Finance"
    }
    assert can_access_record(wrong_role, restricted_document) is False


def test_explain_access_decision_public(public_document, business_analyst):
    """Explain access decision for public records."""
    decision = explain_access_decision(business_analyst, public_document)
    assert decision["granted"] is True
    assert "public" in decision["reason"].lower()


def test_explain_access_decision_denied(confidential_document, business_analyst):
    """Explain access decision for denied access."""
    decision = explain_access_decision(business_analyst, confidential_document)
    assert decision["granted"] is False
    assert "not in allowed_roles" in decision["reason"]


def test_filter_authorized_records(business_analyst, public_document, confidential_document):
    """Filter list of records by authorization."""
    records = [public_document, confidential_document]
    filtered = filter_authorized_records(business_analyst, records)
    assert len(filtered) == 1
    assert filtered[0]["document_id"] == "DOC-022"


def test_can_access_chunk(confidential_document, security_engineer):
    """Chunks inherit permissions from documents."""
    chunk = {
        "chunk_id": "DOC-008-1",
        "document_id": "DOC-008",
        "classification": "confidential",
        "allowed_roles": ["security_engineer"],
        "owner": "Erik Williams",
        "department": "Security"
    }
    assert can_access_chunk(security_engineer, chunk) is True


def test_authenticate_user_success():
    """authenticate_user returns user dict on valid credentials."""
    from secure_semantic_docs.governance.permissions import authenticate_user
    users = {
        "admin": {
            "user_id": "admin",
            "role": "admin",
            "department": "platform",
            "clearance_level": "restricted",
            "password": "admin"
        }
    }
    result = authenticate_user("admin", "admin", users)
    assert result is not None
    assert result["user_id"] == "admin"


def test_authenticate_user_wrong_password():
    """authenticate_user returns None on wrong password."""
    from secure_semantic_docs.governance.permissions import authenticate_user
    users = {
        "admin": {"user_id": "admin", "password": "admin", "role": "admin"}
    }
    result = authenticate_user("admin", "wrongpassword", users)
    assert result is None


def test_authenticate_user_unknown_user():
    """authenticate_user returns None for unknown user_id."""
    from secure_semantic_docs.governance.permissions import authenticate_user
    result = authenticate_user("ghost", "password", {})
    assert result is None
