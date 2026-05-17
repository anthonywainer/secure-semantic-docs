from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import secure_semantic_docs.serving.answer_extractor as answer_extractor
import secure_semantic_docs.serving.result_sanitizer as result_sanitizer
import secure_semantic_docs.serving.retrieval_service as retrieval_service
from secure_semantic_docs.serving.access_context import AccessContext


def _context(query: str, tmp_path: Path, user: dict | None = None) -> AccessContext:
    return AccessContext(
        user=user,
        user_id="user-1",
        query=query,
        top_k=2,
        logs_dir=tmp_path
    )


def test_keyword_search_returns_no_answer_when_query_words_not_found() -> None:
    answer = answer_extractor._keyword_search(
        "missing keywords",
        [{"document_id": "DOC-1", "chunk_text": "nothing relevant here"}]
    )
    assert answer == answer_extractor.NO_AUTHORIZED_ANSWER


def test_get_gold_forbidden_fields_falls_back_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        result_sanitizer,
        "get_sensitive_fields",
        lambda dataset_name, contracts_dir=None: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    assert result_sanitizer.get_gold_forbidden_fields() == result_sanitizer._DEFAULT_GOLD_FORBIDDEN


def test_load_gold_records_handles_missing_paths_success_and_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path
) -> None:
    assert retrieval_service.load_gold_records(tmp_path / "missing") == []

    gold_dir = tmp_path / "gold"
    gold_dir.mkdir()
    assert retrieval_service.load_gold_records(gold_dir) == []

    import pandas as pd

    success_dir = tmp_path / "gold-success"
    success_dir.mkdir()
    pd.DataFrame([{"chunk_id": "c1"}]).to_parquet(success_dir / "part.parquet", index=False)
    assert retrieval_service.load_gold_records(success_dir) == [{"chunk_id": "c1"}]

    parquet_path = gold_dir / "part.parquet"
    parquet_path.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(pd, "read_parquet", lambda path: (_ for _ in ()).throw(ValueError("bad parquet")))
    assert retrieval_service.load_gold_records(gold_dir) == []


def test_load_fact_records_handles_missing_empty_and_multiple_json_objects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path
) -> None:
    assert retrieval_service.load_fact_records(tmp_path / "missing.jsonl") == []

    facts_path = tmp_path / "facts.jsonl"
    facts_path.write_text("   ", encoding="utf-8")
    assert retrieval_service.load_fact_records(facts_path) == []

    facts_path.write_text('{"fact_id":"f1"}\n  {"fact_id":"f2"}\n  ', encoding="utf-8")
    assert retrieval_service.load_fact_records(facts_path) == [{"fact_id": "f1"}, {"fact_id": "f2"}]

    class _StickyStr(str):
        def strip(self, _chars: str | None = None) -> _StickyStr:
            return self

    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(Path, "read_text", lambda self, encoding="utf-8": _StickyStr('{"fact_id":"f1"}   '))
    assert retrieval_service.load_fact_records(Path("unused.jsonl")) == [{"fact_id": "f1"}]


def test_compute_query_embedding_and_decrypt_embedding_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakeSentenceTransformer:
        def __init__(self, model_name: str) -> None:
            captured["model_name"] = model_name

        @staticmethod
        def encode(query: str, **kwargs: object) -> np.ndarray:
            captured["query"] = query
            captured["kwargs"] = kwargs
            return np.array([1.0], dtype=np.float32)

    monkeypatch.setitem(
        __import__("sys").modules,
        "sentence_transformers",
        __import__("types").SimpleNamespace(SentenceTransformer=_FakeSentenceTransformer)
    )
    embedding = retrieval_service._compute_query_embedding("query", model_name="demo-model")
    assert embedding is not None
    assert embedding.tolist() == [1.0]
    assert captured == {
        "model_name": "demo-model",
        "query": "query",
        "kwargs": {"normalize_embeddings": True, "convert_to_numpy": True}
    }

    monkeypatch.setitem(__import__("sys").modules, "sentence_transformers", None)
    assert retrieval_service._compute_query_embedding("query") is None

    assert retrieval_service._decrypt_embedding({"chunk_id": "c1"}, b"key") is None

    monkeypatch.setattr(
        "secure_semantic_docs.security.secretbox_decryptor.secretbox_decrypt",
        lambda ciphertext, nonce, key: b"\x00\x00\x80?"
    )
    decrypted = retrieval_service._decrypt_embedding(
        {"chunk_id": "c1", "embedding_ciphertext": b"x", "embedding_nonce": b"y"},
        b"key"
    )
    assert decrypted is not None
    assert decrypted.tolist() == [1.0]

    monkeypatch.setattr(
        "secure_semantic_docs.security.secretbox_decryptor.secretbox_decrypt",
        lambda ciphertext, nonce, key: (_ for _ in ()).throw(ValueError("boom"))
    )
    assert retrieval_service._decrypt_embedding(
        {"chunk_id": "c1", "embedding_ciphertext": b"x", "embedding_nonce": b"y"},
        b"key"
    ) is None


def test_cosine_similarity_and_rank_by_similarity(monkeypatch: pytest.MonkeyPatch) -> None:
    assert retrieval_service._cosine_similarity(np.array([0.0]), np.array([1.0])) == 0.0

    monkeypatch.setattr(
        retrieval_service,
        "_decrypt_embedding",
        lambda record, key: np.array(record["vector"], dtype=np.float32) if "vector" in record else None
    )
    ranked, decrypted_count = retrieval_service._rank_by_similarity(
        [{"chunk_id": "b", "vector": [0.0, 1.0]}, {"chunk_id": "a", "vector": [1.0, 0.0]}, {"chunk_id": "c"}],
        np.array([1.0, 0.0], dtype=np.float32),
        b"key"
    )

    assert [record["chunk_id"] for record in ranked] == ["a", "b", "c"]
    assert decrypted_count == 2


def test_fact_retrieve_denies_unauthenticated_user(tmp_path: Path) -> None:
    result = retrieval_service.fact_retrieve(
        _context("Who was the Incident commander?", tmp_path, user=None),
        [{"fact_id": "f1", "fact_type": "incident_commander", "subject": "incident"}]
    )
    assert result["handled"] is True
    assert result["access_granted"] is False
    assert result["answer"] == retrieval_service.NO_AUTHORIZED_INFORMATION


def test_matching_facts_and_subject_extraction_helpers() -> None:
    assert retrieval_service._matching_incident_commander_facts("other query", []) == []
    assert retrieval_service._extract_requested_incident_subject("Who was the incident commander?") == ""

    facts = [
        {"fact_id": "f1", "fact_type": "other", "subject": "X"},
        {"fact_id": "f2", "fact_type": "incident_commander", "subject": "Wanted Incident"}
    ]
    matches = retrieval_service._matching_incident_commander_facts(
        "Who was the incident commander of wanted incident?",
        facts
    )
    assert matches == [{"fact_id": "f2", "fact_type": "incident_commander", "subject": "Wanted Incident"}]


def test_merge_candidates_deduplicates_by_candidate_id() -> None:
    merged = retrieval_service._merge_candidates(
        [{"chunk_id": "a"}, {"chunk_id": "a"}],
        [{"chunk_id": "a"}, {"chunk_id": "b"}, {"document_id": "doc-only"}]
    )
    assert merged == [{"chunk_id": "a"}, {"chunk_id": "b"}, {"document_id": "doc-only"}]


def test_governed_retrieve_fact_query_semantic_fallback_branches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path
) -> None:
    user = {"role": "admin", "clearance_level": "restricted"}
    context = _context("Who was the Incident commander of missing incident?", tmp_path, user=user)

    no_candidates = retrieval_service.governed_retrieve(context, [], [])
    assert no_candidates["status"] == "no_authorized_information"
    assert no_candidates["strategy"] == "fact_lookup"

    monkeypatch.setattr(
        retrieval_service,
        "secure_retrieve",
        lambda ctx, _candidates: {"results": [], "filtered_out": ["x"]}
    )
    no_results = retrieval_service.governed_retrieve(context, [{"chunk_id": "x"}], [])
    assert no_results["blocked_count"] == 1
    assert no_results["status"] == "no_authorized_information"

    monkeypatch.setattr(
        retrieval_service,
        "secure_retrieve",
        lambda ctx, _candidates: {
            "results": [
                {
                    "document_id": "DOC-1",
                    "chunk_id": "c1",
                    "classification": "public",
                    "score": 0.9,
                    "source_path": "docs/doc.txt"
                }
            ],
            "filtered_out": ["blocked"]
        }
    )
    with_candidates = retrieval_service.governed_retrieve(context, [{"chunk_id": "c1"}], [])
    assert with_candidates["answer_type"] == "no_fact_answer"
    assert with_candidates["status"] == "no_fact_answer"
    assert with_candidates["blocked_count"] == 1
    assert with_candidates["sources"][0]["chunk_id"] == "c1"


def test_full_semantic_retrieve_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    user = {"role": "admin", "clearance_level": "restricted"}
    context = _context("general query", tmp_path, user=user)
    audit_request_id = "audit-id"

    no_candidates = retrieval_service._full_semantic_retrieve(context, [], audit_request_id)
    assert no_candidates["status"] == "no_authorized_information"

    monkeypatch.setattr(
        retrieval_service,
        "secure_retrieve",
        lambda ctx, _candidates: {"results": [], "filtered_out": ["blocked"]}
    )
    no_results = retrieval_service._full_semantic_retrieve(context, [{"chunk_id": "c1"}], audit_request_id)
    assert no_results["blocked_count"] == 1
    assert no_results["status"] == "no_authorized_information"

    monkeypatch.setattr(
        retrieval_service,
        "secure_retrieve",
        lambda ctx, _candidates: {
            "results": [{"document_id": "DOC-1", "chunk_id": "c1", "classification": "public"}],
            "filtered_out": []
        }
    )
    answered = retrieval_service._full_semantic_retrieve(context, [{"chunk_id": "c1"}], audit_request_id)
    assert answered["answer_type"] == "candidate_list"
    assert answered["sources"] == [{
        "document_id": "DOC-1",
        "chunk_id": "c1",
        "classification": "public",
        "score": "",
        "source_path": ""
    }]


def test_extract_sources_returns_safe_minimal_records() -> None:
    assert retrieval_service._extract_sources([
        {
            "document_id": "DOC-1",
            "chunk_id": "c1",
            "classification": "public",
            "score": 0.5,
            "source_path": "docs/a.txt"
        }
    ]) == [{
        "document_id": "DOC-1",
        "chunk_id": "c1",
        "classification": "public",
        "score": 0.5,
        "source_path": "docs/a.txt"
    }]
