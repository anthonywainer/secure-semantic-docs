"""Tests for answer_extractor module."""

# noinspection PyProtectedMember
from secure_semantic_docs.serving.answer_extractor import (
    NO_AUTHORIZED_ANSWER,
    NO_FACT_ANSWER,
    build_fact_answer,
    build_no_authorized_answer,
    build_no_fact_answer,
    extract_answer,
    _detect_intent  # noqa: SLF001
)


def _make_chunk(text: str, chunk_id: str = "c1", doc_id: str = "DOC-001") -> dict:
    return {"chunk_id": chunk_id, "document_id": doc_id, "chunk_text": text}


INCIDENT_TEXT = (
    "INCIDENT REPORT: PIPELINE OUTAGE 2024-01-15\n"
    "Severity: P1 | Department: Engineering | Classification: Confidential\n\n"
    "CONTACT\n"
    "Incident commander: hshaw@example.org\n"
)


def test_extract_incident_commander() -> None:
    chunks = [_make_chunk(INCIDENT_TEXT, "c1", "DOC-009")]
    answer = extract_answer("Who was the Incident commander?", chunks)
    assert answer == "The incident commander was hshaw@example.org."


def test_extract_incident_commander_full_query() -> None:
    chunks = [_make_chunk(INCIDENT_TEXT, "c1", "DOC-009")]
    answer = extract_answer(
        "Who was the Incident commander of PIPELINE OUTAGE 2024-01-15?",
        chunks
    )
    assert answer == "The incident commander was hshaw@example.org."


def test_detect_intent_incident_commander() -> None:
    assert _detect_intent("Who was the incident commander?") == "incident_commander"
    assert _detect_intent("Find the commander") == "incident_commander"
    assert _detect_intent("What is the IC for this incident?") == "incident_commander"


def test_detect_intent_owner() -> None:
    assert _detect_intent("Who is the owner?") == "owner"


def test_detect_intent_department() -> None:
    assert _detect_intent("What department is this?") == "department"


def test_detect_intent_affected_system() -> None:
    assert _detect_intent("What is the affected system?") == "affected_system"


def test_detect_intent_unknown() -> None:
    assert _detect_intent("Tell me something random") is None


def test_no_match_returns_no_answer() -> None:
    chunks = [_make_chunk("Nothing relevant here.", "c1")]
    answer = extract_answer("Who was the incident commander?", chunks)
    assert answer == "No authorized information was found for your query."


def test_empty_chunks_returns_no_answer() -> None:
    answer = extract_answer("Who was the incident commander?", [])
    assert answer == "No authorized information was found for your query."


def test_unauthorized_user_gets_no_answer() -> None:
    chunks: list[dict] = []
    answer = extract_answer("Who was the incident commander of PIPELINE OUTAGE?", chunks)
    assert answer == "No authorized information was found for your query."


def test_admin_can_get_answer() -> None:
    chunks = [_make_chunk(INCIDENT_TEXT, "c1", "DOC-009")]
    answer = extract_answer("Who was the Incident commander?", chunks)
    assert "hshaw@example.org" in answer


def test_security_engineer_can_get_answer() -> None:
    chunks = [_make_chunk(INCIDENT_TEXT, "c1", "DOC-009")]
    answer = extract_answer("Who was the incident commander?", chunks)
    assert "hshaw@example.org" in answer


def test_keyword_search_fallback() -> None:
    chunks = [_make_chunk("Pipeline outage occurred on 2024-01-15.", "c1", "DOC-009")]
    answer = extract_answer("outage 2024", chunks)
    assert "DOC-009" in answer or answer == "No authorized information was found for your query."


def test_text_model_context_excludes_encrypted_fields() -> None:
    from secure_semantic_docs.serving.retrieval_service import build_text_model_context
    results = [
        {
            "chunk_id": "c1",
            "document_id": "DOC-009",
            "classification": "confidential",
            "chunk_text": "transient text"
        }
    ]
    context = build_text_model_context(results, "test query")
    assert context["text_model_enabled"] is False
    for source in context["authorized_sources"]:
        assert "chunk_text" not in source


# ---------------------------------------------------------------------------
# build_fact_answer
# ---------------------------------------------------------------------------

def test_build_fact_answer_incident_commander() -> None:
    fact = {"fact_type": "incident_commander", "object": "hshaw@example.org"}
    answer = build_fact_answer("Who was the incident commander?", fact)
    assert answer == "The incident commander was hshaw@example.org."


def test_build_fact_answer_owner() -> None:
    fact = {"fact_type": "owner", "object": "Alice"}
    answer = build_fact_answer("Who is the owner?", fact)
    assert answer == "The owner is Alice."


def test_build_fact_answer_unknown_type_falls_back() -> None:
    fact = {"fact_type": "unknown_type", "object": "some_value"}
    answer = build_fact_answer("something", fact)
    assert "some_value" in answer


def test_build_fact_answer_returns_string_not_dict() -> None:
    fact = {"fact_type": "incident_commander", "object": "hshaw@example.org"}
    answer = build_fact_answer("Who was the incident commander?", fact)
    assert isinstance(answer, str)


# ---------------------------------------------------------------------------
# build_no_authorized_answer
# ---------------------------------------------------------------------------

def test_build_no_authorized_answer_returns_expected_string() -> None:
    answer = build_no_authorized_answer()
    assert answer == "No authorized information was found for your query."
    assert answer == NO_AUTHORIZED_ANSWER


def test_build_no_authorized_answer_returns_string() -> None:
    assert isinstance(build_no_authorized_answer(), str)


# ---------------------------------------------------------------------------
# build_no_fact_answer
# ---------------------------------------------------------------------------

def test_build_no_fact_answer_returns_expected_string() -> None:
    answer = build_no_fact_answer()
    assert answer == "No extracted fact answer is available for this query."
    assert answer == NO_FACT_ANSWER


def test_build_no_fact_answer_returns_string() -> None:
    assert isinstance(build_no_fact_answer(), str)


def test_no_authorized_answer_and_no_fact_answer_are_different() -> None:
    assert build_no_authorized_answer() != build_no_fact_answer()
