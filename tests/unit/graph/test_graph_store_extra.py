from __future__ import annotations

import builtins
import json
from pathlib import Path

import pytest

from secure_semantic_docs.graph.graph_store import GraphEdge, GraphNode, GraphStore


class _FakeNxGraph:
    def __init__(self) -> None:
        self._edges = {
            ("root", "child"): {"relation_type": "relates_to"},
            ("root", "ignored"): {"relation_type": "mentions"},
            ("child", "root"): {"relation_type": "relates_to"}
        }

    def __contains__(self, node_id: str) -> bool:
        return node_id in {"root", "child", "ignored"}

    def successors(self, node_id: str) -> list[str]:
        return [target for source, target in self._edges if source == node_id]

    def get_edge_data(self, source_id: str, target_id: str) -> dict[str, str]:
        return self._edges[(source_id, target_id)]


def _public_node(node_id: str, source_chunk_id: str = "chunk-1") -> GraphNode:
    return GraphNode(
        node_id=node_id,
        node_type="entity",
        label=node_id,
        classification="public",
        allowed_roles=[],
        source_chunk_id=source_chunk_id
    )


def test_try_get_nx_returns_cached_graph() -> None:
    store = GraphStore()
    store._nx_graph = {"cached": True}
    assert store._try_get_nx() == {"cached": True}


def test_try_get_nx_handles_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    store = GraphStore()
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "networkx":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert store._try_get_nx() is None


def test_lookup_node_missing_and_lookup_entity_alias() -> None:
    store = GraphStore()
    assert store.lookup_node("missing", {"role": "admin"}) is None
    assert store.lookup_entity("missing", {"role": "admin"}) is None


def test_get_related_returns_empty_when_max_hops_invalid() -> None:
    store = GraphStore()
    assert store.get_related("root", {"role": "admin"}, max_hops=0) == []



def test_get_related_uses_dict_backend_when_networkx_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    store = GraphStore()
    monkeypatch.setattr(store, "_try_get_nx", lambda: None)
    monkeypatch.setattr(store, "_get_related_dict", lambda node_id, user, relation_type, max_hops: [_public_node("child")])
    related = store.get_related("root", None)
    assert [node.node_id for node in related] == ["child"]


def test_get_related_nx_filters_relation_type_and_cycles() -> None:
    store = GraphStore()
    store.add_node(_public_node("child"))
    store.add_node(_public_node("ignored"))

    related = store._get_related_nx(_FakeNxGraph(), "root", None, "relates_to", 2)
    related_ids = sorted(node.node_id for node in related)

    assert related_ids == ["child"]
    assert store._get_related_nx(_FakeNxGraph(), "missing", None, None, 1) == []


def test_get_related_dict_filters_relation_type_and_cycles() -> None:
    store = GraphStore()
    store.add_node(_public_node("root"))
    store.add_node(_public_node("child"))
    store.add_node(_public_node("ignored"))
    store.add_edge(GraphEdge("root", "child", "relates_to"))
    store.add_edge(GraphEdge("root", "ignored", "mentions"))
    store.add_edge(GraphEdge("child", "root", "relates_to"))

    related = store._get_related_dict("root", None, "relates_to", 2)
    related_ids = sorted(node.node_id for node in related)

    assert related_ids == ["child"]


def test_save_without_persist_path_raises() -> None:
    with pytest.raises(RuntimeError, match="persist_path is not configured"):
        GraphStore().save()


def test_load_without_persist_path_is_noop() -> None:
    GraphStore()._load()


def test_load_handles_invalid_json(tmp_path: Path) -> None:
    persist_path = tmp_path / "graph.json"
    persist_path.write_text("not-json", encoding="utf-8")
    store = GraphStore(persist_path=persist_path)
    assert len(store) == 0


def test_load_reads_nodes_and_edges_from_json(tmp_path: Path) -> None:
    persist_path = tmp_path / "graph.json"
    persist_path.write_text(
        json.dumps(
            {
                "nodes": [
                    _public_node("root").to_record(),
                    _public_node("child").to_record()
                ],
                "edges": [
                    {
                        "source_id": "root",
                        "target_id": "child",
                        "relation_type": "relates_to",
                        "confidence": 0.5
                    }
                ]
            }
        ),
        encoding="utf-8"
    )

    store = GraphStore(persist_path=persist_path)

    assert len(store._edges) == 1
    assert store._edges[0].source_id == "root"
    assert store._edges[0].extraction_method == "metadata"
