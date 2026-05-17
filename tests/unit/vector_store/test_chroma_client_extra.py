from __future__ import annotations

import sys
import types

import pytest

import secure_semantic_docs.vector_store.chroma_client as chroma_client
from secure_semantic_docs.vector_store.chroma_client import ChromaConfig


class _FakeCollection:
    def __init__(self) -> None:
        self.upsert_calls: list[dict[str, object]] = []
        self.query_calls: list[dict[str, object]] = []

    def upsert(self, **kwargs):
        self.upsert_calls.append(kwargs)

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        return {
            "ids": [["chunk-1", "chunk-2"]],
            "metadatas": [[{"document_id": "DOC-1"}, {"document_id": "DOC-2"}]],
            "distances": [[0.1, 0.2]]
        }


class _FakeClient:
    def __init__(self, collection: _FakeCollection) -> None:
        self.collection = collection
        self.calls: list[dict[str, object]] = []

    def get_or_create_collection(self, **kwargs):
        self.calls.append(kwargs)
        return self.collection


class _FakeHttpClientFactory:
    def __init__(self, collection: _FakeCollection) -> None:
        self.collection = collection
        self.created: list[tuple[str, int]] = []

    def __call__(self, host: str, port: int):
        self.created.append((host, port))
        return _FakeClient(self.collection)


def test_connect_chroma_import_error_success_and_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "chromadb", None)
    with pytest.raises(ImportError, match="chromadb is required"):
        chroma_client.connect_chroma(ChromaConfig(host="chroma", port=9999))

    collection = _FakeCollection()
    factory = _FakeHttpClientFactory(collection)
    monkeypatch.setitem(sys.modules, "chromadb", types.SimpleNamespace(HttpClient=factory))

    result = chroma_client.connect_chroma()

    assert result is collection
    assert factory.created == [("localhost", 8000)]

    failing_module = types.SimpleNamespace(
        HttpClient=lambda host, port: (_ for _ in ()).throw(RuntimeError("down"))
    )
    monkeypatch.setitem(sys.modules, "chromadb", failing_module)
    with pytest.raises(RuntimeError, match="Could not connect to Chroma"):
        chroma_client.connect_chroma(ChromaConfig(host="bad", port=1))


def test_upsert_candidates_covers_mismatch_skipped_and_empty_records() -> None:
    collection = _FakeCollection()

    with pytest.raises(ValueError, match="length mismatch"):
        chroma_client.upsert_candidates(collection, [{"chunk_id": "c1"}], [])

    count = chroma_client.upsert_candidates(
        collection,
        [{"document_id": "DOC-0"}],
        [[0.1, 0.2]]
    )
    assert count == 0

    count = chroma_client.upsert_candidates(
        collection,
        [
            {"chunk_id": "c1", "document_id": "DOC-1", "allowed_roles": ["admin"]},
            {"document_id": "DOC-2"}
        ],
        [[0.1, 0.2], [0.3, 0.4]]
    )
    assert count == 1
    assert collection.upsert_calls[-1]["ids"] == ["c1"]
    assert collection.upsert_calls[-1]["metadatas"] == [{
        "chunk_id": "c1",
        "document_id": "DOC-1",
        "allowed_roles": "admin"
    }]


def test_query_candidates_builds_safe_result_records(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chroma_client, "_SAFE_METADATA_FIELDS", chroma_client._SAFE_METADATA_FIELDS | {"secret"})
    metadata = chroma_client.build_safe_metadata({"secret": "hidden", "document_id": "DOC-1"})
    assert metadata == {"document_id": "DOC-1"}

    collection = _FakeCollection()
    results = chroma_client.query_candidates(
        collection,
        [0.1, 0.2],
        top_k=3,
        where={"classification": "public"}
    )

    assert collection.query_calls[-1] == {
        "query_embeddings": [[0.1, 0.2]],
        "n_results": 3,
        "include": ["metadatas", "distances"],
        "where": {"classification": "public"}
    }
    assert results == [
        {"document_id": "DOC-1", "chunk_id": "chunk-1", "_chroma_distance": 0.1},
        {"document_id": "DOC-2", "chunk_id": "chunk-2", "_chroma_distance": 0.2}
    ]
