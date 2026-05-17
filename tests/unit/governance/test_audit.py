"""Tests for audit module."""

import json
from pathlib import Path

from secure_semantic_docs.governance import (
    get_audit_summary_for_ui,
    load_audit_events,
    log_access_denied_event,
    log_login_event,
    log_search_event,
)


def test_log_search_event(tmp_path: Path):
    """Test logging search events."""
    request_id = log_search_event(
        user_id="USR-001",
        role="data_engineer",
        query="test query",
        mode="secure",
        returned_ids=["DOC-001", "DOC-002"],
        filtered_out_ids=["DOC-003"],
        access_decisions={"DOC-001": True, "DOC-002": True, "DOC-003": False},
        decrypted_embedding_count=2,
        status="success",
        logs_dir=tmp_path
    )

    assert request_id is not None
    audit_path = tmp_path / "audit_log.jsonl"
    assert audit_path.exists()

    with audit_path.open(encoding="utf-8") as f:
        event = json.loads(f.readline())

    assert event["event_type"] == "search"
    assert event["user_id"] == "USR-001"
    assert event["role"] == "data_engineer"
    assert event["mode"] == "secure"
    assert event["returned_count"] == 2
    assert event["filtered_out_count"] == 1


def test_log_login_event(tmp_path: Path):
    """Test logging login events."""
    request_id = log_login_event(
        user_id="admin",
        role="admin",
        status="success",
        logs_dir=tmp_path
    )

    assert request_id is not None
    audit_path = tmp_path / "audit_log.jsonl"
    assert audit_path.exists()

    with audit_path.open(encoding="utf-8") as f:
        event = json.loads(f.readline())

    assert event["event_type"] == "login"
    assert event["user_id"] == "admin"
    assert event["role"] == "admin"
    assert event["status"] == "success"


def test_log_access_denied_event(tmp_path: Path):
    """Test logging access denied events."""
    request_id = log_access_denied_event(
        user_id="external_viewer",
        role="external_viewer",
        resource_id="DOC-008",
        resource_type="document",
        reason="classification=confidential not in allowed_roles",
        logs_dir=tmp_path
    )

    assert request_id is not None
    with (tmp_path / "audit_log.jsonl").open(encoding="utf-8") as f:
        event = json.loads(f.readline())

    assert event["event_type"] == "access_denied"
    assert event["status"] == "denied"
    assert event["user_id"] == "external_viewer"


def test_load_audit_events(tmp_path: Path):
    """Test loading audit events from file."""
    log_search_event(
        user_id="USR-001",
        role="data_engineer",
        query="query1",
        mode="secure",
        returned_ids=["DOC-001"],
        filtered_out_ids=[],
        access_decisions={"DOC-001": True},
        decrypted_embedding_count=1,
        logs_dir=tmp_path
    )
    log_login_event(user_id="admin", role="admin", logs_dir=tmp_path)

    events = load_audit_events(tmp_path)
    assert len(events) == 2
    assert events[0]["event_type"] == "search"
    assert events[1]["event_type"] == "login"


def test_load_audit_events_empty(tmp_path: Path):
    """Test loading audit events when file does not exist."""
    events = load_audit_events(tmp_path)
    assert events == []


def test_get_audit_summary_admin_sees_all(tmp_path: Path):
    """Admin sees all users' audit events."""
    log_search_event(
        user_id="business_analyst",
        role="business_analyst",
        query="q1",
        mode="secure",
        returned_ids=[],
        filtered_out_ids=[],
        access_decisions={},
        decrypted_embedding_count=0,
        logs_dir=tmp_path
    )
    log_login_event(user_id="admin", role="admin", logs_dir=tmp_path)

    admin = {"user_id": "admin", "role": "admin"}
    events = get_audit_summary_for_ui(admin, logs_dir=tmp_path)
    assert len(events) == 2


def test_get_audit_summary_non_admin_sees_own(tmp_path: Path):
    """Non-admin sees only their own events."""
    log_search_event(
        user_id="business_analyst",
        role="business_analyst",
        query="q1",
        mode="secure",
        returned_ids=[],
        filtered_out_ids=[],
        access_decisions={},
        decrypted_embedding_count=0,
        logs_dir=tmp_path
    )
    log_search_event(
        user_id="external_viewer",
        role="external_viewer",
        query="q2",
        mode="secure",
        returned_ids=[],
        filtered_out_ids=[],
        access_decisions={},
        decrypted_embedding_count=0,
        logs_dir=tmp_path
    )

    user = {"user_id": "business_analyst", "role": "business_analyst"}
    events = get_audit_summary_for_ui(user, logs_dir=tmp_path)
    assert len(events) == 1
    assert events[0]["user_id"] == "business_analyst"


def test_audit_summary_strips_sensitive_fields(tmp_path: Path):
    """Audit summary for UI does not expose returned_ids or access_decisions."""
    log_search_event(
        user_id="admin",
        role="admin",
        query="test",
        mode="secure",
        returned_ids=["DOC-001"],
        filtered_out_ids=["DOC-002"],
        access_decisions={"DOC-001": True, "DOC-002": False},
        decrypted_embedding_count=1,
        logs_dir=tmp_path
    )

    admin = {"user_id": "admin", "role": "admin"}
    events = get_audit_summary_for_ui(admin, logs_dir=tmp_path)
    assert len(events) == 1
    event = events[0]

    assert "returned_ids" not in event
    assert "access_decisions" not in event
    assert "filtered_out_ids" not in event
    assert "returned_count" in event
    assert "filtered_out_count" in event
