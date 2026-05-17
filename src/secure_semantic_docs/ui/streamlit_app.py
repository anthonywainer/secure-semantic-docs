"""Secure Semantic Docs — Governed Retrieval UI.

Canonical Streamlit UI module for the governed retrieval demo.
No direct SQL access. All actions go through the Python permission
and retrieval layer.

Run with:
    streamlit run src/secure_semantic_docs/query_ui.py

.. warning::
    This UI uses demo-only plain-text password authentication.
    It is NOT suitable for production use.
"""

from __future__ import annotations

import logging
from pathlib import Path

import streamlit as st

from secure_semantic_docs.core.settings import BaseSettings
from secure_semantic_docs.governance.audit import log_login_event
from secure_semantic_docs.governance.permissions import authenticate_user, load_users
from secure_semantic_docs.governance.retrieval import (
    governed_search,
    insecure_search,
    load_fact_records,
    load_gold_records
)
from secure_semantic_docs.governance.ui_data import (
    get_audit_summary,
    get_authorized_chunk_summary,
    get_governance_summary
)
from secure_semantic_docs.serving.retrieval_service import is_fact_query

logger = logging.getLogger(BaseSettings.APP_NAME)

_USERS_PATH = (
        BaseSettings.data_dir / "synthetic_data" / "users" / "users.json"
)

_UNSAFE_FIELDS = frozenset({
    "embedding_ciphertext",
    "embedding_nonce",
    "key_id",
    "raw_text",
    "document_hash"
})


def _lakehouse_dir() -> Path:
    return BaseSettings.runtime_dir / "lakehouse"


def _logs_dir() -> Path:
    return BaseSettings.runtime_dir / "logs"


def _safe_record(record: dict) -> dict:
    """Strip any unsafe fields that should never appear in the UI."""
    return {k: v for k, v in record.items() if k not in _UNSAFE_FIELDS}


def _load_candidates(_user_id: str) -> list[dict]:
    """Load gold records as search candidates."""
    return load_gold_records(_lakehouse_dir() / "gold_embeddings")


def _load_facts() -> list[dict]:
    """Load extracted facts for exact governed answers."""
    return load_fact_records(
        BaseSettings.runtime_dir / "metadata" / "facts" / "extracted_facts.jsonl"
    )


def _render_warning_banner() -> None:
    st.warning(
        "**This UI is a controlled educational demo.** "
        "It does not provide direct SQL access. "
        "All actions go through the Python permission and retrieval layer."
    )


def _render_login() -> dict | None:
    """Render the login form. Returns the authenticated user dict or None."""
    st.header("Login")
    users = load_users(_USERS_PATH)

    with st.form("login_form"):
        user_id = st.text_input("User ID") or ""
        password = st.text_input("Password", type="password") or ""
        submitted = st.form_submit_button("Login")

    if not submitted:
        return None

    user = authenticate_user(user_id, password, users)
    if not user:
        log_login_event(
            user_id=str(user_id or ""),
            role="unknown",
            status="denied",
            reason="Invalid credentials",
            logs_dir=_logs_dir()
        )
        st.error("Invalid user ID or password.")
        return None

    log_login_event(
        user_id=str(user_id or ""),
        role=str(user.get("role") or "unknown"),
        status="success",
        logs_dir=_logs_dir()
    )
    return user


def _render_user_info(user: dict) -> None:
    st.success(f"Logged in as **{user.get('name', user.get('user_id', ''))}**")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Role", user.get("role", "—"))
    col2.metric("Department", user.get("department", "—"))
    col3.metric("Clearance", user.get("clearance_level", "—"))
    col4.metric("User ID", user.get("user_id", "—"))


def _render_secure_search(user: dict) -> None:
    st.subheader("Secure Semantic Search")
    st.info(
        "Permissions are enforced before any decryption. "
        "You will only see results you are authorized to access. "
        "Ask natural-language questions and receive structured answers."
    )

    with st.form("secure_search_form"):
        query = st.text_input(
            "Enter your search query",
            placeholder="Who was the Incident commander of PIPELINE OUTAGE 2024-01-15?"
        )
        top_k = st.slider("Max results (top_k)", min_value=1, max_value=20, value=5)
        submitted = st.form_submit_button("Search")

    if not submitted or not query:
        return

    users = load_users(_USERS_PATH)
    candidates = _load_candidates(user.get("user_id", ""))
    facts = _load_facts()

    if not candidates and not facts:
        st.warning("No indexed documents found. Run the pipeline first.")
        return

    if not facts and is_fact_query(query):
        st.warning(
            "No extracted facts were found. "
            "Run the Gold pipeline and verify fact extraction."
        )
        return

    result = governed_search(
        query=query,
        user_id=user.get("user_id", ""),
        candidates=candidates,
        facts=facts,
        top_k=top_k,
        users=users,
        logs_dir=_logs_dir()
    )

    _render_search_result(result)


def _render_search_result(result: dict) -> None:
    """Render a governed search result in structured human-readable form."""
    from secure_semantic_docs.serving.result_sanitizer import sanitize_record  # noqa: PLC0415

    status = result.get("status", "error")
    answer = result.get("answer", "")

    st.subheader("Answer")
    if status == "answered":
        st.success(answer)
    elif status in ("no_authorized_information", "no_fact_answer"):
        st.info(answer)
    else:
        st.error(answer or "An error occurred during retrieval.")

    sources = result.get("sources", [])
    if sources:
        import pandas as pd  # noqa: PLC0415
        st.subheader("Sources")
        display_cols = ["document_id", "chunk_id", "classification", "score", "source_path"]
        rows = [
            {col: sanitize_record(s).get(col, "") for col in display_cols}
            for s in sources
        ]
        non_empty_cols = [
            col for col in display_cols if any(row.get(col) for row in rows)
        ]
        st.dataframe(pd.DataFrame(rows, columns=non_empty_cols), use_container_width=True)

    st.subheader("Retrieval details")
    col1, col2, col3 = st.columns(3)
    col1.metric("Strategy", result.get("strategy", "—"))
    col2.metric("Blocked results", result.get("blocked_count", 0))
    col3.caption(f"Audit ID: `{result.get('audit_request_id', '—')}`")

    with st.expander("Technical details"):
        tech = result.get("technical_details", {})
        st.json(sanitize_record(tech) if tech else {})


def _render_insecure_search(user: dict) -> None:
    st.subheader("Unsafe Comparison Demo")
    st.error(
        "**DEMO ONLY — NOT SAFE FOR PRODUCTION.** "
        "This mode illustrates what happens when permission enforcement is bypassed. "
        "Unauthorized results are shown as blocked — their content is never revealed."
    )

    with st.form("insecure_search_form"):
        query = st.text_input("Enter your search query (unsafe demo)")
        top_k = st.slider("Max results (top_k)", min_value=1, max_value=20, value=5)
        submitted = st.form_submit_button("Run Unsafe Search")

    if not submitted or not query:
        return

    users = load_users(_USERS_PATH)
    candidates = _load_candidates(user.get("user_id", ""))

    if not candidates:
        st.warning("No indexed documents found. Run the pipeline first.")
        return

    result = insecure_search(
        query=query,
        user_id=user.get("user_id", ""),
        candidates=candidates,
        top_k=top_k,
        users=users,
        logs_dir=_logs_dir()
    )

    filtered = result.get("filtered_out", [])
    results = result.get("results", [])

    st.markdown(f"**Authorized results returned:** {len(results)}")
    if filtered:
        st.warning(
            f"{len(filtered)} result(s) were filtered out due to insufficient permissions. "
            "Their content is NOT shown."
        )
        with st.expander("Blocked result IDs (no content exposed)"):
            for blocked_id in filtered:
                st.text(f"  • {blocked_id} — BLOCKED")

    for i, record in enumerate(results, start=1):
        safe = _safe_record(record)
        with st.expander(f"Result {i}: {safe.get('document_id', 'unknown')}"):
            st.json({k: v for k, v in safe.items() if not isinstance(v, (bytes, bytearray))})


def _render_document_summary(user: dict) -> None:
    st.subheader("Your Authorized Documents")
    st.caption("Shows only documents and chunks you have permission to access.")

    bronze_path = _lakehouse_dir() / "bronze_documents"
    silver_path = _lakehouse_dir() / "silver_chunks"
    records = get_authorized_chunk_summary(user, bronze_path, silver_path)

    if not records:
        st.info("No authorized documents found. Run the pipeline first.")
        return

    st.success(f"You can access {len(records)} document(s).")

    import pandas as pd
    display_cols = ["document_id", "title", "classification", "owner", "department", "version"]
    rows = []
    for r in records:
        rows.append({col: r.get(col, "") for col in display_cols})
    st.dataframe(pd.DataFrame(rows), use_container_width=True)


def _render_governance_summary(user: dict) -> None:
    st.subheader("Governance & Catalog Summary")
    st.caption("Shows data asset metadata, lineage, and classification. No sensitive content.")

    entities = get_governance_summary(user, project_root=BaseSettings.project_root)

    if not entities:
        st.info("No governance data available.")
        return

    for entity in entities:
        with st.expander(f"{entity.get('name', '')} ({entity.get('type', '')})"):
            st.write(f"**Owner:** {entity.get('owner', '—')}")
            st.write(f"**Classification:** {entity.get('classification', '—')}")
            st.write(f"**Description:** {entity.get('description', '—')}")
            tags = entity.get("tags", [])
            if tags:
                st.write(f"**Tags:** {', '.join(tags)}")
            upstream = entity.get("lineage_upstream", [])
            downstream = entity.get("lineage_downstream", [])
            if upstream or downstream:
                st.write(f"**Lineage:** {' → '.join(upstream + [entity['id']] + downstream)}")
            notes = entity.get("security_notes", "")
            if notes:
                st.caption(notes)


def _render_audit_summary(user: dict) -> None:
    st.subheader("Audit Log")
    role = user.get("role", "")
    if role == "admin":
        st.caption("Admin view: showing all audit events.")
    else:
        st.caption("Showing only your own audit events.")

    events = get_audit_summary(user, logs_dir=_logs_dir())

    if not events:
        st.info("No audit events found yet.")
        return

    import pandas as pd
    df = pd.DataFrame(events)
    st.dataframe(df, use_container_width=True)


def main() -> None:
    """Main Streamlit app entry point."""
    st.set_page_config(
        page_title="Secure Semantic Docs",
        layout="wide"
    )

    st.title("Secure Semantic Docs — Governed Retrieval UI")
    _render_warning_banner()

    if "user" not in st.session_state:
        st.session_state["user"] = None

    if st.session_state["user"] is None:
        user = _render_login()
        if user:
            st.session_state["user"] = user
            st.rerun()
        else:
            st.markdown("---")
            st.markdown(
                "**Demo credentials:** `admin/admin`, `business_analyst/business`, "
                "`security_engineer/security`, `finance_manager/finance`, "
                "`external_viewer/external`"
            )
        return

    user = st.session_state["user"]
    _render_user_info(user)

    if st.button("Logout"):
        st.session_state["user"] = None
        st.rerun()

    st.markdown("---")

    tab_secure, tab_insecure, tab_docs, tab_gov, tab_audit = st.tabs([
        "Secure Search",
        "Unsafe Demo",
        "My Documents",
        "Governance",
        "Audit Log"
    ])

    with tab_secure:
        _render_secure_search(user)

    with tab_insecure:
        _render_insecure_search(user)

    with tab_docs:
        _render_document_summary(user)

    with tab_gov:
        _render_governance_summary(user)

    with tab_audit:
        _render_audit_summary(user)


if __name__ == "__main__":
    main()
