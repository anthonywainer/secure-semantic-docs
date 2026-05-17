# Future Text Model Integration

## Status

**DISABLED BY DEFAULT.**

The architecture prepares for text model (LLM/RAG) integration but does not
enable it by default. No external API calls are made.

## Current query flow (without text model)

```text
User query
  → authenticate user
  → search extracted facts (exact, permission-filtered)
  → if fact found: return governed answer
  → else: semantic candidate retrieval (embedding search)
       → permission filter candidates
       → sanitize results
       → return authorized source references
  → audit all access
```

Exact answers come from governed extracted facts in
`runtime/metadata/facts/extracted_facts.jsonl`.
Candidate documents are retrieved by embedding similarity against the gold layer.

No decrypted chunk body is available in the current design. Embeddings are used
only for candidate retrieval; the answer surface is the fact store.

## Prepared interface

`build_text_model_context(authorized_results, query, user)` in
`src/secure_semantic_docs/serving/retrieval_service.py` builds a structured
context bundle that a text model could consume.

The bundle always includes:

- `query` — the original user query
- `authorized_sources` — list of `{chunk_id, document_id, classification, owner, department}` for each authorized result
- `user_role` — the authenticated user's role for audit context
- `source_count` — number of authorized sources
- `text_model_enabled: False` — disabled flag, must be explicitly switched on

No raw ciphertexts, nonces, key identifiers, or plaintext chunk text are included.

## Future query flow (with text model)

When text model integration is enabled the flow extends after candidate retrieval:

```text
User query
  → authenticate user
  → search extracted facts (exact, permission-filtered)
  → if fact found: return governed answer
  → semantic candidate retrieval
       → permission filter candidates
       → sanitize candidates (remove all encryption fields)
       → build_text_model_context(authorized_candidates, query, user)
       → retrieve authorized chunk text from a reviewed context source
            (must not expose ciphertext, nonces, or key material)
       → call text model with context bundle
       → model returns grounded natural language answer
       → append source references to response
  → audit: log request_id, user_id, role, source chunk IDs, model id
  → return answer + authorized source references
```

The model only ever sees:

- The user's query
- Sanitized metadata from authorized chunks (classification, owner, department)
- Plaintext content from an explicitly reviewed, access-controlled context source
- Never: ciphertext, nonces, key IDs, or records the user is not authorized to access

## Proposed module structure

```
src/secure_semantic_docs/serving/
├── retrieval_service.py      # existing — builds context bundle
├── text_model.py             # NEW — model invocation and response shaping
└── context_source.py         # NEW — reviewed authorized plaintext context source
```

### `text_model.py` interface sketch

```python
from __future__ import annotations

from typing import Any, Protocol


class TextModel(Protocol):
    """Minimal interface for a text generation model."""

    def generate(self, prompt: str, context: str) -> str:
        """Generate a grounded answer given a prompt and context."""
        ...


def call_text_model(
    context_bundle: dict[str, Any],
    model: TextModel
) -> dict[str, Any]:
    """Invoke the text model with an authorized context bundle.

    Only enabled when text_model_enabled is True in the bundle.
    Logs an audit event for every invocation. Never passes ciphertext
    or unauthorized records to the model.
    """
    if not context_bundle.get("text_model_enabled"):
        return {"answer": None, "text_model_enabled": False}
    ...
```

### `context_source.py` interface sketch

```python
from __future__ import annotations

from pathlib import Path


def load_authorized_chunk_text(
    chunk_ids: list[str],
    user_roles: list[str],
    source_path: Path
) -> dict[str, str]:
    """Return plaintext chunk content for chunk_ids the user is authorized to read.

    This source must:
    - enforce role-based access per record before returning any text
    - never return records outside the caller's allowed_roles
    - never return encryption fields
    - be backed by a separate access-controlled store, not the gold parquet layer
    """
    ...
```

## Security requirements before enabling

Before enabling text model integration, every item below must be satisfied:

1. **Only authorized context.** The model must never receive records the user is
   not authorized to access. Permission filtering must happen before any model
   invocation.

2. **No encryption internals.** The model context must never include
   `chunk_text_ciphertext`, `chunk_text_nonce`, `chunk_text_key_id`,
   `embedding_ciphertext`, `embedding_nonce`, or `key_id`.

3. **Audit all prompts.** Every model invocation must be logged to the audit trail
   with `request_id`, `user_id`, `role`, model identifier, and the source chunk IDs
   used as context.

4. **Local or private model preferred.** Use an on-premise or private model to avoid
   sending document content to external APIs. If an external API is used, it must be
   approved through a documented security review.

5. **No external calls by default.** The default configuration must not make any
   external network requests. Text model integration must be explicitly opted in.

6. **Reviewed context source.** A separate reviewed module must own the authorized
   plaintext context. It must not reintroduce persisted chunk text via the gold layer
   or any intermediate store that bypasses role filtering.

7. **Grounding only.** The model must use retrieved content only to ground its answer.
   It must not be prompted to speculate beyond the authorized context.

## Enabling (future)

To enable text model integration:

1. Set `text_model_enabled: true` in the serving configuration.
2. Implement `serving/text_model.py` with `call_text_model(context_bundle, model)`.
3. Implement `serving/context_source.py` with `load_authorized_chunk_text(...)`.
4. Add a corresponding audit event for each model call in the audit logger.
5. Add tests that verify:
    - only authorized context reaches the model
    - encryption fields are never present in the context bundle
    - each invocation produces an audit record
    - disabling the flag returns no model answer without calling the model

## Recommended local model options

| Model                                     | Notes                                                             |
|-------------------------------------------|-------------------------------------------------------------------|
| `llama3` via Ollama                       | Fully local, no external calls, easy to run with `ollama serve`   |
| `mistral` via Ollama                      | Good instruction-following, fully local                           |
| `all-MiniLM-L6-v2` (SentenceTransformers) | Already in the stack — retrieval only, not generation             |
| OpenAI API                                | Requires approved security review; content leaves the environment |

For local development, Ollama is the recommended path because it runs on the same machine
with no outbound network traffic.
