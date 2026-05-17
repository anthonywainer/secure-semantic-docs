# Security Boundaries

## Architecture overview

```text
User query
    │
    ▼
Streamlit UI (controlled semantic retrieval)
    │   No raw SQL. No embedding internals. No plaintext ciphertext.
    ▼
Serving Layer (Python)
    │   authenticate → access context → query planner
    ▼
┌───────────────────────┐
│ Graph Index           │  Relationship + fact lookup
│ (NetworkX)            │  Permission-aware filtering
└───────────────────────┘
         +
┌───────────────────────┐
│ Chroma Vector Index   │  ANN candidate retrieval
│ (Docker)              │  No text, no keys stored
└───────────────────────┘
    │
    ▼
Permission filter (Python — can_access_record)
    │   FILTER FIRST
    ▼
Governed fact lookup
    │   ANSWER FROM EXTRACTED FACTS
    ▼
Sanitize result (strip forbidden fields)
    │   SANITIZE ALWAYS
    ▼
Audit log (append-only JSONL)
    │   AUDIT ALWAYS
    ▼
Authorized results returned to Streamlit
```

## Facts vs Embeddings

Embeddings and facts serve distinct roles and are stored separately:

| Concern                            | Storage table                                  | Purpose                         |
|------------------------------------|------------------------------------------------|---------------------------------|
| Vector similarity search           | `gold_embeddings`                              | ANN candidate retrieval         |
| Authorized exact answer generation | `runtime/metadata/facts/extracted_facts.jsonl` | Permission-filtered fact lookup |

- **Embeddings** are for candidate retrieval. Chroma stores the float32 vectors as a fast index.
  The retrieval service uses embedding similarity to find relevant chunk IDs.
- **Extracted facts** are for authorized exact answers. Facts are created during processing from
  transient chunk text and persisted without raw chunk text.
- No storage layer persists plaintext chunk text or encrypted chunk text.

## SQL access boundary

```text
Business user
    │
    ▼
Superset SQL UI (governed dashboards only)
    │   No semantic retrieval. No raw lakehouse access.
    ▼
Trino SQL engine
    │   lakehouse.safe.* views only (for non-admin)
    │   lakehouse.raw.* (admin only)
    ▼
OPA / File-based ACL
    │   Schema + table + column enforcement
    ▼
Parquet files in runtime/lakehouse/
```

## What each layer must NOT expose

| Layer               | Never expose                                                                                          |
|---------------------|-------------------------------------------------------------------------------------------------------|
| Streamlit           | Raw SQL, embedding_ciphertext, nonce, key_id, decrypted embeddings, unauthorized text, raw chunk text |
| Superset            | Raw gold table, ciphertext, nonce, key_id, decrypted content, secret keys                             |
| Chroma              | raw_text, nonce, key_id, secrets                                                                      |
| Graph               | sensitive_label for unauthorized users, raw_text                                                      |
| Trino safe views    | embedding_ciphertext, embedding_nonce, key_id                                                         |
| Text model (future) | Must receive only authorized, sanitized decrypted context                                             |
| Extracted facts     | Unauthorized facts, raw source text, encryption internals                                             |

## Source of truth hierarchy

1. **Encrypted lakehouse plus governed facts** — authoritative source of truth
2. **Chroma** — candidate index only (can be rebuilt from Gold)
3. **Graph** — relationship index only (can be rebuilt from Silver/Gold)
4. **Trino** — governed SQL query layer (reads from lakehouse, does not own data)

## Text model future integration

Future LLM/RAG integration must:

1. Receive ONLY authorized, sanitized context from the retrieval service.
2. Never have access to raw chunk text.
3. Never have access to embedding ciphertexts, nonces, or key identifiers.
4. Never have access to unauthorized chunk text.
5. Have all prompts logged to the audit trail.
6. Be disabled by default (`text_model_enabled: false`).

See `docs/future_text_model.md`.
