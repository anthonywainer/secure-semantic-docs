# Secure Governed UI

## Overview

The Streamlit UI provides a controlled, permission-aware interface for demonstrating
secure semantic document retrieval. It does **not** provide a SQL editor or direct
table access.

## Security Principles

- **No direct SQL access.** Trino, and Superset are intentionally excluded.
  Direct SQL engines can expose internal tables, raw text, encrypted payloads, nonces,
  key identifiers, and sensitive metadata.
- **Predefined actions only.** Users interact through named panels. There is no free
  query interface.
- **Permission-aware retrieval.** All search and data access calls go through the
  Python governance and retrieval layer.
- **Sanitized summaries.** The UI never shows `embedding_ciphertext`, `embedding_nonce`,
  `key_id`, raw embeddings, or unauthorized text.
- **Audit logging.** Every login and retrieval action is written to `runtime/logs/audit_log.jsonl`.

## Running the UI

```bash
pip install streamlit pandas
streamlit run src/secure_semantic_docs/query_ui.py
```

The UI starts at `http://localhost:8501`.

## Demo Credentials

| User ID             | Password   | Role              | Clearance    |
|---------------------|------------|-------------------|--------------|
| `admin`             | `admin`    | admin             | restricted   |
| `business_analyst`  | `business` | business_analyst  | internal     |
| `security_engineer` | `security` | security_engineer | confidential |
| `finance_manager`   | `finance`  | finance_manager   | confidential |
| `external_viewer`   | `external` | external_viewer   | public       |

> **Warning:** This is demo-only plain-text authentication. Not suitable for production.

## UI Panels

### 1. Secure Search

- Accepts a natural language query.
- Calls `secure_search()` — permissions enforced before any decryption.
- Only authorized results are displayed.
- Sanitized: no encrypted fields, no raw embeddings.

### 2. Unsafe Comparison Demo

- Illustrates what happens without proper permission enforcement.
- Unauthorized results are shown only as blocked IDs — their content is never revealed.
- Clearly labeled as demo-only unsafe mode.

### 3. My Documents

- Shows documents the logged-in user is authorized to access.
- No raw text, no encrypted fields, no embeddings.

### 4. Governance

- Shows the asset catalog: names, types, lineage, classifications.
- No sensitive content.

### 5. Audit Log

- Admin: sees all events.
- Non-admin: sees only their own events.
- Sensitive fields like `returned_ids` and `access_decisions` are stripped from display.

## Limitations

- This demo uses plain-text password comparison. In production, use bcrypt + JWT.
- The Streamlit UI is for educational demonstration only.