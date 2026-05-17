from secure_semantic_docs import query_ui
from secure_semantic_docs.ui import streamlit_app


def test_query_ui_reexports_streamlit_main() -> None:
    assert query_ui.main is streamlit_app.main
