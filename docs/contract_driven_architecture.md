# Contract-Driven Architecture

## Overview

`secure-semantic-docs` uses a **contract-driven architecture** where a single
canonical source in `config/contracts/` defines all metadata, schemas, lineage, roles
and access policies. Every downstream layer — governance, permissions, catalog
export, quality checks, retrieval and UI — derives its behaviour from these
contracts rather than from hardcoded constants.

## Contract files

```
config/contracts/
├── datasets.yml           # One entry per dataset: fields, required, sensitive, forbidden, lineage
├── lineage.yml            # Canonical lineage graph (source → target edges)
├── schemas/               # DDL files for Spark/Iceberg schema registration
│   ├── bronze_documents.ddl
│   ├── silver_chunks.ddl
│   ├── gold_embeddings.ddl
│   └── embed_cache.ddl
└── security/
    ├── roles.yml           # Role name → clearance_level
    ├── classifications.yml # Ordered classification levels + clearance hierarchy
    └── access_policies.yml # Classification → access rules (clearance, role, dept)
```

### `config/contracts/datasets.yml`

Defines every dataset (landing → bronze → silver → gold → serving → ui → audit).
Each entry specifies:

| Key                                       | Purpose                                                                   |
|-------------------------------------------|---------------------------------------------------------------------------|
| `fields`                                  | Column list with `required`, `sensitive`, `forbidden_in_safe_views` flags |
| `required_fields`                         | Fields that must be non-null (used by `quality.py`)                       |
| `sensitive_fields`                        | Fields excluded from UI and safe views (used by `result_sanitizer.py`)    |
| `forbidden_fields`                        | Alias for safe-view exclusion; used by Trino views                        |
| `lineage_upstream` / `lineage_downstream` | Direct lineage (also in `lineage.yml`)                                    |

### `config/contracts/lineage.yml`

The canonical lineage graph. `catalog.py` reads this to populate `lineage_graph.edges`
in the OpenMetadata export. DDL `TBLPROPERTIES` are kept for Spark/Iceberg tooling
but `lineage.yml` is the authoritative source.

### `config/contracts/security/roles.yml`

Maps every role name to its `clearance_level`. Combined with `classifications.yml`
(which defines `clearance_order`) this allows the system to reason about clearance
without any Python constants.

## How modules use contracts

| Module                 | What it reads from contracts                                                               |
|------------------------|--------------------------------------------------------------------------------------------|
| `permissions.py`       | `access_policies.yml` — classification policies (clearance levels, role check, dept match) |
| `catalog.py`           | `datasets.yml` + `lineage.yml` — entity list and lineage graph                             |
| `quality.py`           | `datasets.yml` — required fields and safe-view constraints                                 |
| `result_sanitizer.py`  | `datasets.yml` `gold_embeddings.sensitive_fields` — fields to strip                        |
| `retrieval_service.py` | `result_sanitizer.py` (which reads contracts)                                              |
| `ui/streamlit_app.py`  | Indirectly via `ui_data.py` → `catalog.py` → contracts                                     |

## Security invariants enforced by contracts

1. `gold_embeddings.forbidden_fields` = `[embedding_ciphertext, embedding_nonce, key_id]`
   — these fields are stripped by `result_sanitizer.py` before any result leaves the retrieval layer.

2. `access_policies.yml` `admin_sees_decrypted_embeddings: false` and
   `admin_sees_secret_keys: false` — admin role does not automatically bypass
   embedding or key exposure.

3. `missing_classification: deny` — records without a classification are denied
   by default.

4. `unknown_user: deny` — unauthenticated access is limited to `public` records.

## Adding a new dataset

1. Add an entry to `config/contracts/datasets.yml`.
2. Add a DDL file to `config/contracts/schemas/` if it needs a Spark schema.
3. Add lineage edges to `config/contracts/lineage.yml`.
4. Re-export the catalog: the `generate_openmetadata_assets` call picks up the new entry automatically.
5. No Python changes needed unless the dataset requires custom quality checks.

## Adding a new role

1. Add an entry to `config/contracts/security/roles.yml` with `clearance_level`.
2. Add the user to `data/synthetic_data/users/users.json` with the matching `role`.
3. Permissions are evaluated against the policy in `access_policies.yml` — no Python changes needed.
