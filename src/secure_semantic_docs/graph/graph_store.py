"""Graph relationship and explainability index.

Uses NetworkX for in-memory graph operations with JSON persistence.
NetworkX is imported lazily and is optional — the module degrades gracefully.

The graph is not the source of truth. It is an index for fast relationship
lookup and retrieval explainability. The encrypted lakehouse remains authoritative.

Graph nodes must include classification and allowed_roles so permission-aware
filtering can be applied before any data is returned.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from secure_semantic_docs.core.settings import BaseSettings
from secure_semantic_docs.governance.permissions import can_access_record

logger = logging.getLogger(BaseSettings.APP_NAME)

_FORBIDDEN_LABEL_FIELDS: frozenset[str] = frozenset({
    'sensitive_label',
    'raw_text'
})


@dataclass
class GraphNode:
    """A node in the relationship graph.

    Attributes
    ----------
    node_id
        Unique node identifier.
    node_type
        Type of node: document, chunk, entity, concept.
    label
        Human-readable label (must not contain sensitive content).
    classification
        Security classification of this node.
    allowed_roles
        Roles permitted to see this node's content.
    department
        Owning department if applicable.
    source_chunk_id
        The chunk this node was extracted from.
    source_document_id
        The document this node was extracted from.
    confidence
        Extraction confidence score [0.0, 1.0].
    extraction_method
        How the node was extracted (e.g. metadata, keyword, future_llm).
    extra
        Additional non-sensitive metadata.
    """

    node_id: str
    node_type: str
    label: str
    classification: str
    allowed_roles: list[str] = field(default_factory=list)
    department: str = ''
    source_chunk_id: str = ''
    source_document_id: str = ''
    confidence: float = 1.0
    extraction_method: str = 'metadata'
    extra: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        """Convert to a dict for permission checking and serialization."""
        return {
            'node_id': self.node_id,
            'node_type': self.node_type,
            'label': self.label,
            'classification': self.classification,
            'allowed_roles': self.allowed_roles,
            'department': self.department,
            'source_chunk_id': self.source_chunk_id,
            'source_document_id': self.source_document_id,
            'confidence': self.confidence,
            'extraction_method': self.extraction_method,
            'extra': dict(self.extra)
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> GraphNode:
        """Reconstruct a GraphNode from a serialized dict."""
        return cls(
            node_id=record['node_id'],
            node_type=record.get('node_type', 'entity'),
            label=record.get('label', ''),
            classification=record.get('classification', 'internal'),
            allowed_roles=record.get('allowed_roles') or [],
            department=record.get('department', ''),
            source_chunk_id=record.get('source_chunk_id', ''),
            source_document_id=record.get('source_document_id', ''),
            confidence=float(record.get('confidence', 1.0)),
            extraction_method=record.get('extraction_method', 'metadata'),
            extra=record.get('extra') or {}
        )


@dataclass
class GraphEdge:
    """A directed edge between two graph nodes.

    Attributes
    ----------
    source_id
        Source node identifier.
    target_id
        Target node identifier.
    relation_type
        Type of relationship: relates_to, part_of, mentions, derived_from.
    confidence
        Edge confidence score [0.0, 1.0].
    extraction_method
        How the edge was extracted.
    """

    source_id: str
    target_id: str
    relation_type: str
    confidence: float = 1.0
    extraction_method: str = 'metadata'


class GraphStore:
    """Permission-aware graph index for relationship lookup and explainability.

    Backed by NetworkX when available, falls back to a simple adjacency dict.
    Persists to JSON for cross-process durability.

    Parameters
    ----------
    persist_path
        Optional JSON file path for persistence. When None, operates in memory only.
    """

    def __init__(self, persist_path: Path | str | None = None) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []
        self._persist_path = Path(persist_path) if persist_path else None
        self._nx_graph: Any = None

        if self._persist_path and self._persist_path.exists():
            self._load()

    def _try_get_nx(self) -> Any:
        """Return a NetworkX DiGraph if networkx is available, else None."""
        if self._nx_graph is not None:
            return self._nx_graph

        try:
            import networkx as nx  # noqa: PLC0415
        except ImportError:
            logger.debug('networkx not installed; using dict-based graph backend')
            return None

        graph = nx.DiGraph()
        for node in self._nodes.values():
            graph.add_node(node.node_id, **node.to_record())
        for edge in self._edges:
            graph.add_edge(
                edge.source_id,
                edge.target_id,
                relation_type=edge.relation_type,
                confidence=edge.confidence,
                extraction_method=edge.extraction_method
            )
        self._nx_graph = graph
        return self._nx_graph

    def add_node(self, node: GraphNode) -> None:
        """Add or replace a node in the graph.

        Parameters
        ----------
        node
            GraphNode to add.
        """
        self._nodes[node.node_id] = node
        self._nx_graph = None

    def add_edge(self, edge: GraphEdge) -> None:
        """Add a directed edge between two nodes.

        Parameters
        ----------
        edge
            GraphEdge connecting source_id → target_id.
        """
        self._edges.append(edge)
        self._nx_graph = None

    def lookup_node(
            self,
            node_id: str,
            user: dict[str, Any] | None = None
    ) -> GraphNode | None:
        """Look up a single node by ID, applying permission check.

        Parameters
        ----------
        node_id
            Node identifier to look up.
        user
            Authenticated user record. None = unauthenticated (public only).

        Returns
        -------
        GraphNode | None
            The node if found and user is authorized, else None.
        """
        node = self._nodes.get(node_id)
        if node is None:
            return None
        if can_access_record(user, node.to_record()):
            return node
        logger.debug('Access denied to graph node %s for user %s', node_id, user)
        return None

    def lookup_entity(
            self,
            node_id: str,
            user: dict[str, Any] | None = None
    ) -> GraphNode | None:
        """Look up an entity node by ID with permission filtering."""
        return self.lookup_node(node_id, user)

    def get_related(
            self,
            node_id: str,
            user: dict[str, Any] | None = None,
            relation_type: str | None = None,
            max_hops: int = 1
    ) -> list[GraphNode]:
        """Return nodes related to a given node, filtered by user permissions.

        Parameters
        ----------
        node_id
            Source node ID.
        user
            Authenticated user. None = unauthenticated (public only).
        relation_type
            Filter by edge type. None = all types.
        max_hops
            Maximum traversal depth (1 = direct neighbors only).

        Returns
        -------
        list[GraphNode]
            Authorized related nodes.
        """
        if max_hops < 1:
            return []

        nx_graph = self._try_get_nx()
        if nx_graph is not None:
            return self._get_related_nx(nx_graph, node_id, user, relation_type, max_hops)
        return self._get_related_dict(node_id, user, relation_type, max_hops)

    def _get_related_nx(
            self,
            nx_graph: Any,
            node_id: str,
            user: dict[str, Any] | None,
            relation_type: str | None,
            max_hops: int
    ) -> list[GraphNode]:
        """NetworkX-backed related node lookup."""
        if node_id not in nx_graph:
            return []

        reachable: set[str] = set()
        frontier = {node_id}
        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for current_node_id in frontier:
                for neighbor in nx_graph.successors(current_node_id):
                    if relation_type is not None:
                        edge_data = nx_graph.get_edge_data(current_node_id, neighbor) or {}
                        if edge_data.get('relation_type') != relation_type:
                            continue
                    if neighbor == node_id or neighbor in reachable:
                        continue
                    next_frontier.add(neighbor)
                    reachable.add(neighbor)
            frontier = next_frontier

        authorized_nodes: list[GraphNode] = []
        for related_node_id in reachable:
            node = self._nodes.get(related_node_id)
            if node and can_access_record(user, node.to_record()):
                authorized_nodes.append(node)
        return authorized_nodes

    def _get_related_dict(
            self,
            node_id: str,
            user: dict[str, Any] | None,
            relation_type: str | None,
            max_hops: int
    ) -> list[GraphNode]:
        """Dict-based related node lookup when networkx is unavailable."""
        reachable: set[str] = set()
        frontier = {node_id}
        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for current_node_id in frontier:
                for edge in self._edges:
                    if edge.source_id != current_node_id:
                        continue
                    if relation_type is not None and edge.relation_type != relation_type:
                        continue
                    if edge.target_id == node_id or edge.target_id in reachable:
                        continue
                    next_frontier.add(edge.target_id)
                    reachable.add(edge.target_id)
            frontier = next_frontier

        authorized_nodes: list[GraphNode] = []
        for related_node_id in reachable:
            node = self._nodes.get(related_node_id)
            if node and can_access_record(user, node.to_record()):
                authorized_nodes.append(node)
        return authorized_nodes

    def find_by_source_chunk(
            self,
            chunk_id: str,
            user: dict[str, Any] | None = None
    ) -> list[GraphNode]:
        """Return all nodes derived from a given chunk, filtered by permissions.

        Parameters
        ----------
        chunk_id
            Source chunk identifier.
        user
            Authenticated user.

        Returns
        -------
        list[GraphNode]
            Authorized nodes that reference this chunk as source.
        """
        authorized_nodes: list[GraphNode] = []
        for node in self._nodes.values():
            if node.source_chunk_id != chunk_id:
                continue
            if can_access_record(user, node.to_record()):
                authorized_nodes.append(node)
        return authorized_nodes

    @staticmethod
    def to_safe_dict(node: GraphNode) -> dict[str, Any]:
        """Return a sanitized dict for a graph node.

        Parameters
        ----------
        node
            GraphNode to sanitize.

        Returns
        -------
        dict[str, Any]
            Safe representation of the node.
        """
        record = node.to_record()
        for forbidden_name in _FORBIDDEN_LABEL_FIELDS:
            record.pop(forbidden_name, None)

        extra = record.get('extra')
        if isinstance(extra, dict):
            record['extra'] = {
                key: value
                for key, value in extra.items()
                if key not in _FORBIDDEN_LABEL_FIELDS
            }

        return record

    def save(self) -> None:
        """Persist the graph to JSON at the configured persist_path.

        Raises
        ------
        RuntimeError
            When persist_path is not configured.
        """
        if self._persist_path is None:
            raise RuntimeError('persist_path is not configured; cannot save graph')

        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'nodes': [node.to_record() for node in self._nodes.values()],
            'edges': [
                {
                    'source_id': edge.source_id,
                    'target_id': edge.target_id,
                    'relation_type': edge.relation_type,
                    'confidence': edge.confidence,
                    'extraction_method': edge.extraction_method
                }
                for edge in self._edges
            ]
        }
        self._persist_path.write_text(
            json.dumps(payload, indent=2),
            encoding='utf-8'
        )
        logger.info(
            'Saved graph with %d nodes, %d edges to %s',
            len(self._nodes),
            len(self._edges),
            self._persist_path
        )

    def _load(self) -> None:
        """Load graph from JSON at persist_path."""
        if self._persist_path is None:
            return

        try:
            payload = json.loads(self._persist_path.read_text(encoding='utf-8'))
            for node_record in payload.get('nodes', []):
                self._nodes[node_record['node_id']] = GraphNode.from_record(node_record)
            for edge_record in payload.get('edges', []):
                self._edges.append(
                    GraphEdge(
                        source_id=edge_record['source_id'],
                        target_id=edge_record['target_id'],
                        relation_type=edge_record['relation_type'],
                        confidence=float(edge_record.get('confidence', 1.0)),
                        extraction_method=edge_record.get('extraction_method', 'metadata')
                    )
                )
        except (json.JSONDecodeError, KeyError, OSError, TypeError, ValueError) as exc:
            logger.warning('Could not load graph from %s: %s', self._persist_path, exc)
            return

        logger.info(
            'Loaded graph with %d nodes, %d edges from %s',
            len(self._nodes),
            len(self._edges),
            self._persist_path
        )

    def __len__(self) -> int:
        return len(self._nodes)
