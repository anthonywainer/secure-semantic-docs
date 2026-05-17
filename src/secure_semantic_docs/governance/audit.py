"""Audit logging for search and access decisions."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from secure_semantic_docs.core.settings import BaseSettings

logger = logging.getLogger(BaseSettings.APP_NAME)


def _current_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def get_audit_path(logs_dir: Path | str) -> Path:
    """Get the audit log file path.

    Parameters
    ----------
    logs_dir
        Directory for logs.

    Returns
    -------
    Path
        Path to audit_log.jsonl.
    """
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / "audit_log.jsonl"


def write_audit_event(
        event: dict, logs_dir: Path | str = "runtime/logs"
) -> None:
    """Write an audit event to the audit log.

    Parameters
    ----------
    event
        Audit event dict with timestamp, request_id, user_id, role, etc.
    logs_dir
        Directory for logs.
    """
    audit_path = get_audit_path(logs_dir)
    with audit_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def log_search_event(
        user_id: str,
        role: str,
        query: str,
        mode: str,
        returned_ids: list[str],
        filtered_out_ids: list[str],
        access_decisions: dict[str, bool],
        decrypted_embedding_count: int,
        status: str = "success",
        logs_dir: Path | str = "runtime/logs",
) -> str:
    """Log a search event to audit.

    Parameters
    ----------
    user_id
        User identifier.
    role
        User role.
    query
        Search query string.
    mode
        "secure" or "insecure".
    returned_ids
        List of returned document/chunk IDs.
    filtered_out_ids
        List of filtered-out IDs due to permissions.
    access_decisions
        Dict mapping ID to access decision.
    decrypted_embedding_count
        Count of embeddings decrypted.
    status
        Event status (success, denied, error).
    logs_dir
        Directory for logs.

    Returns
    -------
    str
        request_id for the logged event.
    """
    request_id = str(uuid4())
    event = {
        "timestamp": _current_timestamp(),
        "request_id": request_id,
        "event_type": "search",
        "user_id": user_id,
        "role": role,
        "query": query,
        "mode": mode,
        "returned_ids": returned_ids,
        "returned_count": len(returned_ids),
        "filtered_out_ids": filtered_out_ids,
        "filtered_out_count": len(filtered_out_ids),
        "access_decisions": access_decisions,
        "decrypted_embedding_count": decrypted_embedding_count,
        "status": status
    }
    write_audit_event(event, logs_dir)
    return request_id


def log_login_event(
        user_id: str,
        role: str,
        status: str = "success",
        reason: str = "",
        logs_dir: Path | str = "runtime/logs",
) -> str:
    """Log a login event to audit.

    Parameters
    ----------
    user_id
        User identifier.
    role
        User role (or "unknown" on failure).
    status
        "success" or "denied".
    reason
        Optional reason for failure.
    logs_dir
        Directory for logs.

    Returns
    -------
    str
        request_id for the logged event.
    """
    request_id = str(uuid4())
    event = {
        "timestamp": _current_timestamp(),
        "request_id": request_id,
        "event_type": "login",
        "user_id": user_id,
        "role": role,
        "status": status,
        "reason": reason
    }
    write_audit_event(event, logs_dir)
    return request_id


def log_access_denied_event(
        user_id: str,
        role: str,
        resource_id: str,
        resource_type: str,
        reason: str,
        logs_dir: Path | str = "runtime/logs",
) -> str:
    """Log an access denied event to audit.

    Parameters
    ----------
    user_id
        User identifier.
    role
        User role.
    resource_id
        ID of the resource that was denied.
    resource_type
        Type of resource (e.g. "document", "chunk", "embedding").
    reason
        Reason for denial.
    logs_dir
        Directory for logs.

    Returns
    -------
    str
        request_id for the logged event.
    """
    request_id = str(uuid4())
    event = {
        "timestamp": _current_timestamp(),
        "request_id": request_id,
        "event_type": "access_denied",
        "user_id": user_id,
        "role": role,
        "resource_id": resource_id,
        "resource_type": resource_type,
        "reason": reason,
        "status": "denied"
    }
    write_audit_event(event, logs_dir)
    return request_id


def load_audit_events(logs_dir: Path | str = "runtime/logs") -> list[dict]:
    """Load all audit events from the audit log.

    Parameters
    ----------
    logs_dir
        Directory for logs.

    Returns
    -------
    list[dict]
        List of audit event dicts.
    """
    audit_path = get_audit_path(logs_dir)
    if not audit_path.exists():
        return []

    events = []
    with audit_path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    return events


def get_audit_summary_for_ui(
        user: dict,
        logs_dir: Path | str = "runtime/logs",
) -> list[dict]:
    """Return audit events filtered for the UI based on user role.

    Admin users see all events. Non-admin users see only their own events.
    Sensitive fields are stripped from all events.

    Parameters
    ----------
    user
        The authenticated user record.
    logs_dir
        Directory for logs.

    Returns
    -------
    list[dict]
        Sanitized audit events accessible to this user.
    """
    events = load_audit_events(logs_dir)
    role = user.get("role", "")
    user_id = user.get("user_id", "")

    if role != "admin":
        events = [e for e in events if e.get("user_id") == user_id]

    safe_events = []
    for event in events:
        safe_events.append({
            "timestamp": event.get("timestamp", ""),
            "event_type": event.get("event_type", ""),
            "user_id": event.get("user_id", ""),
            "role": event.get("role", ""),
            "query": event.get("query", ""),
            "mode": event.get("mode", ""),
            "returned_count": event.get("returned_count", 0),
            "filtered_out_count": event.get("filtered_out_count", 0),
            "status": event.get("status", ""),
            "reason": event.get("reason", "")
        })

    return safe_events
