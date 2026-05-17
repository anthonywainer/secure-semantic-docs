from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import secure_semantic_docs.ui.streamlit_app as app


class _ContextManager:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _patch_form(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app.st, "form", lambda name: _ContextManager())


def _patch_expander(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app.st, "expander", lambda label: _ContextManager())


def _patch_tabs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app.st, "tabs", lambda labels: [_ContextManager() for _ in labels])


def test_helper_functions_strip_unsafe_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(app, "load_gold_records", lambda path: captured.setdefault("gold_path", path) or [])
    monkeypatch.setattr(app, "load_fact_records", lambda path: captured.setdefault("facts_path", path) or [])

    assert app._lakehouse_dir().name == "lakehouse"
    assert app._logs_dir().name == "logs"
    assert app._safe_record({"document_id": "DOC-1", "key_id": "secret"}) == {"document_id": "DOC-1"}
    app._load_candidates("admin")
    app._load_facts()
    assert str(captured["gold_path"]).endswith("gold_embeddings")
    assert str(captured["facts_path"]).endswith("runtime/metadata/facts/extracted_facts.jsonl")


def test_render_warning_banner_calls_streamlit_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    warning = MagicMock()
    monkeypatch.setattr(app.st, "warning", warning)
    app._render_warning_banner()
    warning.assert_called_once()


def test_render_login_returns_none_when_not_submitted(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_form(monkeypatch)
    monkeypatch.setattr(app, "load_users", lambda path: {})
    monkeypatch.setattr(app.st, "header", lambda message: None)
    monkeypatch.setattr(app.st, "text_input", lambda label, **kwargs: "")
    monkeypatch.setattr(app.st, "form_submit_button", lambda label: False)
    assert app._render_login() is None


def test_render_login_invalid_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_form(monkeypatch)
    error = MagicMock()
    login_event = MagicMock()
    values = iter(["ghost", "bad-password"])

    monkeypatch.setattr(app, "load_users", lambda path: {"ghost": {}})
    monkeypatch.setattr(app, "authenticate_user", lambda user_id, password, users: None)
    monkeypatch.setattr(app, "log_login_event", login_event)
    monkeypatch.setattr(app.st, "header", lambda message: None)
    monkeypatch.setattr(app.st, "text_input", lambda label, **kwargs: next(values))
    monkeypatch.setattr(app.st, "form_submit_button", lambda label: True)
    monkeypatch.setattr(app.st, "error", error)

    assert app._render_login() is None
    login_event.assert_called_once()
    error.assert_called_once_with("Invalid user ID or password.")


def test_render_login_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_form(monkeypatch)
    success_user = {"user_id": "admin", "role": "admin"}
    values = iter(["admin", "admin"])
    login_event = MagicMock()

    monkeypatch.setattr(app, "load_users", lambda path: {"admin": success_user})
    monkeypatch.setattr(app, "authenticate_user", lambda user_id, password, users: success_user)
    monkeypatch.setattr(app, "log_login_event", login_event)
    monkeypatch.setattr(app.st, "header", lambda message: None)
    monkeypatch.setattr(app.st, "text_input", lambda label, **kwargs: next(values))
    monkeypatch.setattr(app.st, "form_submit_button", lambda label: True)

    assert app._render_login() == success_user
    login_event.assert_called_once()


def test_render_user_info(monkeypatch: pytest.MonkeyPatch) -> None:
    success = MagicMock()
    columns = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
    monkeypatch.setattr(app.st, "success", success)
    monkeypatch.setattr(app.st, "columns", lambda count: columns)

    app._render_user_info({
        "name": "Alice",
        "role": "admin",
        "department": "platform",
        "clearance_level": "restricted",
        "user_id": "admin"
    })

    success.assert_called_once()
    assert columns[0].metric.call_args[0] == ("Role", "admin")
    assert columns[3].metric.call_args[0] == ("User ID", "admin")


def test_render_secure_search_handles_empty_query_and_missing_data(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_form(monkeypatch)
    monkeypatch.setattr(app.st, "subheader", lambda message: None)
    monkeypatch.setattr(app.st, "info", lambda message: None)
    monkeypatch.setattr(app.st, "slider", lambda *args, **kwargs: 5)

    monkeypatch.setattr(app.st, "text_input", lambda *args, **kwargs: "")
    monkeypatch.setattr(app.st, "form_submit_button", lambda label: True)
    app._render_secure_search({"user_id": "admin"})

    warning = MagicMock()
    monkeypatch.setattr(app.st, "text_input", lambda *args, **kwargs: "general query")
    monkeypatch.setattr(app, "load_users", lambda path: {"admin": {}})
    monkeypatch.setattr(app, "_load_candidates", lambda user_id: [])
    monkeypatch.setattr(app, "_load_facts", list)
    monkeypatch.setattr(app.st, "warning", warning)

    app._render_secure_search({"user_id": "admin"})
    warning.assert_called_once_with("No indexed documents found. Run the pipeline first.")


def test_render_secure_search_warns_for_missing_fact_store(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_form(monkeypatch)
    warning = MagicMock()
    monkeypatch.setattr(app.st, "subheader", lambda message: None)
    monkeypatch.setattr(app.st, "info", lambda message: None)
    monkeypatch.setattr(app.st, "slider", lambda *args, **kwargs: 5)
    monkeypatch.setattr(app.st, "text_input", lambda *args, **kwargs: "Who was the Incident commander?")
    monkeypatch.setattr(app.st, "form_submit_button", lambda label: True)
    monkeypatch.setattr(app, "load_users", lambda path: {"admin": {}})
    monkeypatch.setattr(app, "_load_candidates", lambda user_id: [{"chunk_id": "c1"}])
    monkeypatch.setattr(app, "_load_facts", list)
    monkeypatch.setattr(app.st, "warning", warning)

    app._render_secure_search({"user_id": "admin"})
    warning.assert_called_once()


def test_render_secure_search_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_form(monkeypatch)
    render_result = MagicMock()
    monkeypatch.setattr(app.st, "subheader", lambda message: None)
    monkeypatch.setattr(app.st, "info", lambda message: None)
    monkeypatch.setattr(app.st, "slider", lambda *args, **kwargs: 5)
    monkeypatch.setattr(app.st, "text_input", lambda *args, **kwargs: "general query")
    monkeypatch.setattr(app.st, "form_submit_button", lambda label: True)
    monkeypatch.setattr(app, "load_users", lambda path: {"admin": {"role": "admin"}})
    monkeypatch.setattr(app, "_load_candidates", lambda user_id: [{"chunk_id": "c1"}])
    monkeypatch.setattr(app, "_load_facts", lambda: [{"fact_id": "f1"}])
    monkeypatch.setattr(app, "governed_search", lambda **kwargs: {"status": "answered", "answer": "ok"})
    monkeypatch.setattr(app, "_render_search_result", render_result)

    app._render_secure_search({"user_id": "admin"})
    render_result.assert_called_once_with({"status": "answered", "answer": "ok"})


def test_render_search_result_covers_statuses_and_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_expander(monkeypatch)
    success = MagicMock()
    info = MagicMock()
    error = MagicMock()
    dataframe = MagicMock()
    json_mock = MagicMock()
    columns = [MagicMock(), MagicMock(), MagicMock()]

    monkeypatch.setattr(app.st, "subheader", lambda message: None)
    monkeypatch.setattr(app.st, "success", success)
    monkeypatch.setattr(app.st, "info", info)
    monkeypatch.setattr(app.st, "error", error)
    monkeypatch.setattr(app.st, "dataframe", dataframe)
    monkeypatch.setattr(app.st, "json", json_mock)
    monkeypatch.setattr(app.st, "columns", lambda count: columns)

    app._render_search_result({
        "status": "answered",
        "answer": "Answer text",
        "strategy": "semantic",
        "blocked_count": 1,
        "audit_request_id": "audit-id",
        "sources": [
            {
                "document_id": "DOC-1",
                "chunk_id": "c1",
                "classification": "public",
                "score": 0.9,
                "source_path": "docs/a.txt",
                "key_id": "secret"
            }
        ],
        "technical_details": {"safe": True, "password": "hidden"}
    })
    success.assert_called_once_with("Answer text")
    dataframe.assert_called_once()
    json_mock.assert_called_once_with({"safe": True})

    app._render_search_result({"status": "no_authorized_information", "answer": "No access"})
    info.assert_called_with("No access")

    app._render_search_result({"status": "error", "answer": "Boom"})
    error.assert_called_with("Boom")


def test_render_insecure_search_handles_empty_query_and_no_candidates(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_form(monkeypatch)
    monkeypatch.setattr(app.st, "subheader", lambda message: None)
    monkeypatch.setattr(app.st, "error", lambda message: None)
    monkeypatch.setattr(app.st, "slider", lambda *args, **kwargs: 5)

    monkeypatch.setattr(app.st, "text_input", lambda *args, **kwargs: "")
    monkeypatch.setattr(app.st, "form_submit_button", lambda label: True)
    app._render_insecure_search({"user_id": "admin"})

    warning = MagicMock()
    monkeypatch.setattr(app.st, "text_input", lambda *args, **kwargs: "query")
    monkeypatch.setattr(app, "load_users", lambda path: {"admin": {}})
    monkeypatch.setattr(app, "_load_candidates", lambda user_id: [])
    monkeypatch.setattr(app.st, "warning", warning)
    app._render_insecure_search({"user_id": "admin"})
    warning.assert_called_once_with("No indexed documents found. Run the pipeline first.")


def test_render_insecure_search_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_form(monkeypatch)
    _patch_expander(monkeypatch)
    warning = MagicMock()
    markdown = MagicMock()
    json_mock = MagicMock()
    text = MagicMock()
    monkeypatch.setattr(app.st, "subheader", lambda message: None)
    monkeypatch.setattr(app.st, "error", lambda message: None)
    monkeypatch.setattr(app.st, "slider", lambda *args, **kwargs: 5)
    monkeypatch.setattr(app.st, "text_input", lambda *args, **kwargs: "query")
    monkeypatch.setattr(app.st, "form_submit_button", lambda label: True)
    monkeypatch.setattr(app, "load_users", lambda path: {"admin": {}})
    monkeypatch.setattr(app, "_load_candidates", lambda user_id: [{"chunk_id": "c1"}])
    monkeypatch.setattr(
        app,
        "insecure_search",
        lambda **kwargs: {
            "filtered_out": ["blocked-1"],
            "results": [{"document_id": "DOC-1", "key_id": "secret"}]
        }
    )
    monkeypatch.setattr(app.st, "warning", warning)
    monkeypatch.setattr(app.st, "markdown", markdown)
    monkeypatch.setattr(app.st, "json", json_mock)
    monkeypatch.setattr(app.st, "text", text)

    app._render_insecure_search({"user_id": "admin"})

    warning.assert_called()
    markdown.assert_called_with("**Authorized results returned:** 1")
    text.assert_called_once()
    json_mock.assert_called_once_with({"document_id": "DOC-1"})


def test_render_document_governance_and_audit_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_expander(monkeypatch)
    dataframe = MagicMock()
    info = MagicMock()
    success = MagicMock()
    write = MagicMock()
    caption = MagicMock()

    monkeypatch.setattr(app.st, "subheader", lambda message: None)
    monkeypatch.setattr(app.st, "caption", caption)
    monkeypatch.setattr(app.st, "info", info)
    monkeypatch.setattr(app.st, "success", success)
    monkeypatch.setattr(app.st, "dataframe", dataframe)
    monkeypatch.setattr(app.st, "write", write)

    monkeypatch.setattr(app, "get_authorized_chunk_summary", lambda user, bronze, silver: [])
    app._render_document_summary({"user_id": "admin"})
    info.assert_called_with("No authorized documents found. Run the pipeline first.")

    info.reset_mock()
    monkeypatch.setattr(
        app,
        "get_authorized_chunk_summary",
        lambda user, bronze, silver: [{
            "document_id": "DOC-1",
            "title": "Doc",
            "classification": "public",
            "owner": "Alice",
            "department": "Ops",
            "version": "1"
        }]
    )
    app._render_document_summary({"user_id": "admin"})
    success.assert_called_with("You can access 1 document(s).")

    monkeypatch.setattr(app, "get_governance_summary", lambda user, project_root: [])
    app._render_governance_summary({"user_id": "admin"})
    info.assert_called_with("No governance data available.")

    info.reset_mock()
    monkeypatch.setattr(
        app,
        "get_governance_summary",
        lambda user, project_root: [{
            "id": "gold_embeddings",
            "name": "Gold Embeddings",
            "type": "Table",
            "owner": "platform",
            "classification": "confidential",
            "description": "Embeddings",
            "tags": ["gold"],
            "lineage_upstream": ["silver_chunks"],
            "lineage_downstream": ["api"],
            "security_notes": "Governed"
        }]
    )
    app._render_governance_summary({"user_id": "admin"})
    write.assert_any_call("**Owner:** platform")
    caption.assert_any_call("Governed")

    monkeypatch.setattr(app, "get_audit_summary", lambda user, logs_dir: [])
    app._render_audit_summary({"user_id": "analyst", "role": "analyst"})
    info.assert_called_with("No audit events found yet.")

    monkeypatch.setattr(app, "get_audit_summary", lambda user, logs_dir: [{"event_type": "search"}])
    app._render_audit_summary({"user_id": "admin", "role": "admin"})
    dataframe.assert_called()


def test_main_covers_login_flow_logout_and_tab_rendering(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tabs(monkeypatch)
    rerun = MagicMock()
    markdown = MagicMock()
    monkeypatch.setattr(app.st, "set_page_config", lambda **kwargs: None)
    monkeypatch.setattr(app.st, "title", lambda message: None)
    monkeypatch.setattr(app, "_render_warning_banner", lambda: None)
    monkeypatch.setattr(app.st, "rerun", rerun)
    monkeypatch.setattr(app.st, "markdown", markdown)

    monkeypatch.setattr(app.st, "session_state", {}, raising=False)
    monkeypatch.setattr(app, "_render_login", lambda: None)
    app.main()
    markdown.assert_called()

    monkeypatch.setattr(app.st, "session_state", {}, raising=False)
    monkeypatch.setattr(app, "_render_login", lambda: {"user_id": "admin"})
    app.main()
    assert app.st.session_state["user"] == {"user_id": "admin"}
    rerun.assert_called()

    monkeypatch.setattr(app.st, "session_state", {"user": {"user_id": "admin", "role": "admin"}}, raising=False)
    monkeypatch.setattr(app, "_render_user_info", lambda user: None)
    monkeypatch.setattr(app.st, "button", lambda label: True)
    app.main()
    assert app.st.session_state["user"] is None

    monkeypatch.setattr(app.st, "session_state", {"user": {"user_id": "admin", "role": "admin"}}, raising=False)
    monkeypatch.setattr(app.st, "button", lambda label: False)
    secure = MagicMock()
    insecure = MagicMock()
    docs = MagicMock()
    gov = MagicMock()
    audit = MagicMock()
    monkeypatch.setattr(app, "_render_secure_search", secure)
    monkeypatch.setattr(app, "_render_insecure_search", insecure)
    monkeypatch.setattr(app, "_render_document_summary", docs)
    monkeypatch.setattr(app, "_render_governance_summary", gov)
    monkeypatch.setattr(app, "_render_audit_summary", audit)
    app.main()
    secure.assert_called_once()
    insecure.assert_called_once()
    docs.assert_called_once()
    gov.assert_called_once()
    audit.assert_called_once()
