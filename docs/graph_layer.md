# Graph Layer

## Role in the architecture

The graph layer is a **relationship and explainability index**. It is not the source of truth.

It enables:

- Fast fact lookup by entity type or chunk reference
- Relationship traversal (e.g. "what documents mention this entity?")
- Retrieval explainability ("why was this chunk returned?")
- Source chunk tracing

## Implementation

NetworkX-backed in-memory graph with JSON persistence.
No Neo4j required for the current milestone.

## Node types

| Type     | Description                                   |
|----------|-----------------------------------------------|
| document | A source document                             |
| chunk    | A text chunk from silver layer                |
| entity   | A fact or entity extracted from a chunk       |
| concept  | An abstract concept linking multiple entities |

## Edge types

| Type         | Direction        | Description                     |
|--------------|------------------|---------------------------------|
| part_of      | chunk → document | Chunk belongs to document       |
| mentions     | chunk → entity   | Chunk mentions an entity        |
| relates_to   | entity → entity  | General relationship            |
| derived_from | entity → chunk   | Entity was extracted from chunk |

## Permission model

Every graph node includes `classification` and `allowed_roles`.
`GraphStore.get_related()` and `GraphStore.lookup_node()` filter by
`can_access_record()` before returning any node data.

Sensitive node labels (`sensitive_label`, `raw_text`) are never exposed
regardless of permissions.

The graph never stores or exposes plaintext chunk text. The graph only stores
safe metadata fields, fact references, classification, and allowed_roles.

## Retrieval strategies

The serving layer supports three retrieval strategies:

- `vector_first` — Chroma ANN search, then permission filter
- `graph_first` — Graph relationship lookup, then Chroma for ranking
- `hybrid` — Both, merged with deduplication

## Module

`src/secure_semantic_docs/graph/graph_store.py`
