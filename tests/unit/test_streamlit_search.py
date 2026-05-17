"""Tests for fact-based search in the Streamlit UI layer."""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import secure_semantic_docs.ui.streamlit_app as streamlit_module
from secure_semantic_docs.serving.retrieval_service import is_fact_query


# ---------------------------------------------------------------------------
# Source-level checks
# ---------------------------------------------------------------------------

def _ui_source() -> str:
    return Path(inspect.getfile(streamlit_module)).read_text(encoding="utf-8")


_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F9FF"
    "\U00002600-\U000027BF"
    "\U0000FE00-\U0000FEFF"
    "]+",
    re.UNICODE
)


def test_streamlit_ui_contains_no_emojis() -> None:
    """streamlit_app.py must not contain any emoji characters."""
    source = _ui_source()
    matches = _EMOJI_PATTERN.findall(source)
    assert not matches, f"Found emoji(s) in streamlit_app.py: {matches}"


def test_tab_names_contain_no_emojis() -> None:
    """Tab names passed to st.tabs() must not include emoji characters."""
    source = _ui_source()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "tabs"
        ):
            for arg in node.args:
                if isinstance(arg, ast.List):
                    for elt in arg.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            assert not _EMOJI_PATTERN.search(elt.value), (
                                f"Tab name contains emoji: {elt.value!r}"
                            )


# ---------------------------------------------------------------------------
# Fact query detection
# ---------------------------------------------------------------------------

def test_incident_commander_query_detected_as_fact_query() -> None:
    """'incident commander' queries must be detected as fact queries."""
    assert is_fact_query("Who was the Incident commander of PIPELINE OUTAGE 2024-01-15?")


def test_generic_query_not_detected_as_fact_query() -> None:
    """Non-incident-commander queries must not be treated as fact queries."""
    assert not is_fact_query("What is our data retention policy?")


# ---------------------------------------------------------------------------
# Missing facts diagnostic
# ---------------------------------------------------------------------------

def _make_mock_user(user_id: str = "admin", role: str = "admin") -> dict:
    return {"user_id": user_id, "role": role, "name": user_id}


def test_empty_facts_shows_diagnostic_not_permission_error() -> None:
    """When the facts file is empty and a fact query is asked, show a diagnostic."""
    with (
        patch.object(streamlit_module.st, "form") as mock_form,
        patch.object(streamlit_module.st, "text_input", return_value="Who was the Incident commander of PIPELINE OUTAGE 2024-01-15?"),
        patch.object(streamlit_module.st, "slider", return_value=5),
        patch.object(streamlit_module.st, "form_submit_button", return_value=True),
        patch("secure_semantic_docs.ui.streamlit_app.load_users", return_value={}),
        patch("secure_semantic_docs.ui.streamlit_app._load_candidates", return_value=[{"doc": "x"}]),
        patch("secure_semantic_docs.ui.streamlit_app._load_facts", return_value=[]),
        patch.object(streamlit_module.st, "warning") as mock_warning,
        patch("secure_semantic_docs.ui.streamlit_app.governed_search") as mock_search,
    ):
        mock_form.return_value.__enter__ = MagicMock(return_value=None)
        mock_form.return_value.__exit__ = MagicMock(return_value=False)

        streamlit_module._render_secure_search(_make_mock_user())

    mock_warning.assert_called_once()
    warning_message = mock_warning.call_args[0][0]
    assert "No extracted facts" in warning_message
    assert "Gold pipeline" in warning_message
    mock_search.assert_not_called()


def test_non_empty_facts_does_not_show_diagnostic() -> None:
    """When facts are present, governed_search is called without the facts diagnostic."""
    stub_fact = {
        "fact_id": "fact-abc",
        "fact_type": "incident_commander",
        "subject": "PIPELINE OUTAGE 2024-01-15",
        "predicate": "HAS_INCIDENT_COMMANDER",
        "object": "hshaw@example.org",
        "document_id": "DOC-009",
        "chunk_id": "DOC-009-001",
        "classification": "confidential",
        "allowed_roles": ["security_engineer"],
        "department": "Engineering",
        "source_path": "confidential/DOC-009_incident.txt",
        "confidence": 0.98,
        "extraction_method": "regex:v1:document_aware",
        "created_at": "2026-01-01T00:00:00Z"
    }
    stub_result = {
        "answer": "The incident commander was hshaw@example.org.",
        "answer_type": "fact_answer",
        "status": "answered",
        "strategy": "fact_lookup",
        "sources": [],
        "blocked_count": 0,
        "audit_request_id": "test-id",
        "technical_details": {}
    }

    with (
        patch.object(streamlit_module.st, "form") as mock_form,
        patch.object(streamlit_module.st, "text_input", return_value="Who was the Incident commander of PIPELINE OUTAGE 2024-01-15?"),
        patch.object(streamlit_module.st, "slider", return_value=5),
        patch.object(streamlit_module.st, "form_submit_button", return_value=True),
        patch("secure_semantic_docs.ui.streamlit_app.load_users", return_value={}),
        patch("secure_semantic_docs.ui.streamlit_app._load_candidates", return_value=[]),
        patch("secure_semantic_docs.ui.streamlit_app._load_facts", return_value=[stub_fact]),
        patch("secure_semantic_docs.ui.streamlit_app.governed_search", return_value=stub_result) as mock_search,
        patch("secure_semantic_docs.ui.streamlit_app._render_search_result"),
        patch.object(streamlit_module.st, "warning") as mock_warning,
    ):
        mock_form.return_value.__enter__ = MagicMock(return_value=None)
        mock_form.return_value.__exit__ = MagicMock(return_value=False)

        streamlit_module._render_secure_search(_make_mock_user())

    mock_search.assert_called_once()
    # No "No extracted facts" warning
    for call in mock_warning.call_args_list:
        if call.args:
            assert "No extracted facts" not in call.args[0]
