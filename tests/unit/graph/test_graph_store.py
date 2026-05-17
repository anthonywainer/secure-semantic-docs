"""Tests for graph store module."""

from pathlib import Path
from typing import Any

import pytest

from secure_semantic_docs.graph.graph_store import GraphEdge, GraphNode, GraphStore


@pytest.fixture
def public_node() -> GraphNode:
    return GraphNode(
        node_id='entity-001',
        node_type='entity',
        label='PySpark',
        classification='public',
        allowed_roles=[],
        source_chunk_id='DOC-022-1',
        source_document_id='DOC-022'
    )


@pytest.fixture
def confidential_node() -> GraphNode:
    return GraphNode(
        node_id='entity-002',
        node_type='entity',
        label='Security Audit',
        classification='confidential',
        allowed_roles=['security_engineer'],
        department='security',
        source_chunk_id='DOC-008-1',
        source_document_id='DOC-008'
    )


@pytest.fixture
def graph_with_nodes(
    public_node: GraphNode,
    confidential_node: GraphNode
) -> GraphStore:
    store = GraphStore()
    store.add_node(public_node)
    store.add_node(confidential_node)
    store.add_edge(
        GraphEdge(
            source_id='entity-001',
            target_id='entity-002',
            relation_type='relates_to'
        )
    )
    return store


@pytest.fixture
def external_user() -> dict[str, str]:
    return {
        'user_id': 'external_viewer',
        'role': 'external_viewer',
        'clearance_level': 'public',
        'department': 'external'
    }


@pytest.fixture
def security_user() -> dict[str, str]:
    return {
        'user_id': 'security_engineer',
        'role': 'security_engineer',
        'clearance_level': 'confidential',
        'department': 'security'
    }



def test_lookup_public_node_accessible(
    graph_with_nodes: GraphStore,
    external_user: dict[str, str]
) -> None:
    node = graph_with_nodes.lookup_node('entity-001', external_user)
    assert node is not None
    assert node.node_id == 'entity-001'



def test_lookup_confidential_node_denied(
    graph_with_nodes: GraphStore,
    external_user: dict[str, str]
) -> None:
    node = graph_with_nodes.lookup_node('entity-002', external_user)
    assert node is None



def test_lookup_confidential_node_authorized(
    graph_with_nodes: GraphStore,
    security_user: dict[str, str]
) -> None:
    node = graph_with_nodes.lookup_node('entity-002', security_user)
    assert node is not None
    assert node.node_id == 'entity-002'



def test_get_related_filters_by_permissions(
    graph_with_nodes: GraphStore,
    external_user: dict[str, str]
) -> None:
    related = graph_with_nodes.get_related('entity-001', external_user)
    related_ids = [node.node_id for node in related]
    assert 'entity-002' not in related_ids



def test_get_related_authorized_user_sees_related(
    graph_with_nodes: GraphStore,
    security_user: dict[str, str]
) -> None:
    related = graph_with_nodes.get_related('entity-001', security_user)
    related_ids = [node.node_id for node in related]
    assert 'entity-002' in related_ids



def test_find_by_source_chunk_public(
    graph_with_nodes: GraphStore,
    external_user: dict[str, str]
) -> None:
    results = graph_with_nodes.find_by_source_chunk('DOC-022-1', external_user)
    assert len(results) == 1
    assert results[0].node_id == 'entity-001'



def test_find_by_source_chunk_confidential_denied(
    graph_with_nodes: GraphStore,
    external_user: dict[str, str]
) -> None:
    results = graph_with_nodes.find_by_source_chunk('DOC-008-1', external_user)
    assert len(results) == 0



def test_to_safe_dict_removes_forbidden_labels(
    graph_with_nodes: GraphStore,
    public_node: GraphNode
) -> None:
    public_node.extra['sensitive_label'] = 'SECRET LABEL'
    record = graph_with_nodes.to_safe_dict(public_node)
    assert 'sensitive_label' not in record
    assert 'raw_text' not in record
    assert 'sensitive_label' not in record['extra']



def test_graph_node_round_trip(public_node: GraphNode) -> None:
    record = public_node.to_record()
    restored = GraphNode.from_record(record)
    assert restored.node_id == public_node.node_id
    assert restored.classification == public_node.classification



def test_graph_store_len(graph_with_nodes: GraphStore) -> None:
    assert len(graph_with_nodes) == 2



def test_graph_persistence(
    tmp_path: Path,
    public_node: GraphNode,
    confidential_node: GraphNode
) -> None:
    persist_file = tmp_path / 'graph.json'
    store = GraphStore(persist_path=persist_file)
    store.add_node(public_node)
    store.add_node(confidential_node)
    store.save()

    assert persist_file.exists()
    loaded = GraphStore(persist_path=persist_file)
    assert len(loaded) == 2
    assert 'entity-001' in loaded._nodes
    assert 'entity-002' in loaded._nodes



def test_build_text_model_context_disabled() -> None:
    from secure_semantic_docs.serving.retrieval_service import build_text_model_context

    results: list[dict[str, str]] = [
        {'chunk_id': 'x', 'document_id': 'd', 'classification': 'public'}
    ]
    context = build_text_model_context(results, 'test query')
    assert context['text_model_enabled'] is False
    assert len(context['authorized_sources']) == 1



def test_build_text_model_context_no_forbidden_fields() -> None:
    from secure_semantic_docs.serving.retrieval_service import build_text_model_context

    results: list[dict[str, Any]] = [
        {
            'chunk_id': 'x',
            'document_id': 'd',
            'classification': 'public',
            'embedding_ciphertext': b'secret',
            'key_id': 'k'
        }
    ]
    context = build_text_model_context(results, 'test query')
    for source in context['authorized_sources']:
        assert 'embedding_ciphertext' not in source
        assert 'key_id' not in source



def test_opa_data_contains_expected_roles() -> None:
    root = Path(__file__).resolve().parents[4]
    users_path = root / 'config/opa/data/users_roles.json'
    if not users_path.exists():
        pytest.skip('OPA data file not found')
    data = users_path.read_text(encoding='utf-8')
    roles = set(__import__('json').loads(data).get('users_roles', {}).values())
    expected = {
        'admin',
        'business_analyst',
        'security_engineer',
        'finance_manager',
        'external_viewer'
    }
    assert expected.issubset(roles)



def test_opa_forbidden_columns_defined() -> None:
    root = Path(__file__).resolve().parents[4]
    tables_path = root / 'config/opa/data/table_policies.json'
    if not tables_path.exists():
        pytest.skip('OPA table_policies.json not found')
    data = tables_path.read_text(encoding='utf-8')
    blocked = __import__('json').loads(data).get('blocked_columns', [])
    assert 'embedding_ciphertext' in blocked
    assert 'embedding_nonce' in blocked
    assert 'key_id' in blocked
