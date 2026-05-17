# Trino, OPA, and Superset

## Trino SQL Engine

Trino provides governed SQL access to the lakehouse Parquet files.

### Connector

Trino 406 with the Hive connector and file-based metastore.
Queries Parquet files directly via `file:///data/lakehouse/`.

### Schema model

| Schema           | Access     | Purpose                             |
|------------------|------------|-------------------------------------|
| `lakehouse.raw`  | Admin only | Raw tables with all fields          |
| `lakehouse.safe` | All roles  | Governed views, no sensitive fields |

### Safe views

| View                              | Description                                          |
|-----------------------------------|------------------------------------------------------|
| `safe.bronze_documents`           | Bronze without internal fields                       |
| `safe.silver_chunks`              | Silver without policy internals                      |
| `safe.gold_embedding_catalog`     | Gold without ciphertext/nonce/key_id                 |
| `safe.v_bronze_documents_catalog` | Verbose catalog alias                                |
| `safe.v_silver_chunks_catalog`    | Verbose catalog alias                                |
| `safe.v_gold_embedding_catalog`   | Verbose catalog alias                                |
| `safe.v_public_chunks`            | Silver rows with classification=public               |
| `safe.v_internal_chunks`          | Silver rows with public+internal                     |
| `safe.v_audit_events`             | Audit events (admin only, when Parquet export ready) |

### Access control

Two enforcement layers:

1. **Trino file-based ACL** (`config/trino/security/rules.json`) — active enforcement
2. **OPA policy** (`config/opa/policies/trino_authz.rego`) — documented intent

## OPA Policy Engine

OPA defines the intended authorization model for Trino queries.

### Current status

OPA is deployed as a Docker service and the policies are written.
Full OPA-Trino wiring requires the `trino-opa-authorizer` plugin (available
as a separate Trino plugin jar). This is documented as the next milestone.

### Policy rules

- `admin` — access to raw + safe schemas
- `business_analyst`, `data_engineer` — safe schema, most views
- `security_engineer`, `finance_manager` — safe schema, most views
- `external_viewer` — safe schema, public-only views (`v_public_chunks`)

### Blocked columns (all roles)

`embedding_ciphertext`, `embedding_nonce`, `key_id`, `raw_text`, `decrypted_embedding`, `password`, `secret`

### OPA-Trino wiring (next milestone)

To wire OPA with Trino:

1. Download `trino-opa-authorizer-{version}.jar`.
2. Place in Trino's `plugin/` directory.
3. Add to `config/trino/etc/access-control.properties`:
   ```properties
   access-control.name=opa
   opa.policy.uri=http://opa:8181/v1/data/trino/authz/allow
   ```
4. Restart Trino.
5. Test: `curl -X POST http://localhost:8181/v1/data/trino/authz/allow -d '{...}'`

## Superset SQL UI

Superset connects to Trino and exposes only governed datasets.

### Connection

Superset → Trino (via trino://admin@trino:8080/lakehouse)

### Governed datasets to register

Register these datasets in Superset pointing to `lakehouse.safe.*` views:

- `safe.v_bronze_documents_catalog`
- `safe.v_silver_chunks_catalog`
- `safe.v_gold_embedding_catalog`
- `safe.v_public_chunks`
- `safe.v_internal_chunks`

### What Superset must NOT expose

- `lakehouse.raw.*` tables
- Any field containing ciphertext, nonce, or key_id
- Decrypted content or plaintext embeddings

### Demo users

| Username          | Password | Role              |
|-------------------|----------|-------------------|
| admin             | admin    | Platform admin    |
| business_analyst  | business | Business analyst  |
| security_engineer | security | Security engineer |
| finance_manager   | finance  | Finance manager   |
| external_viewer   | external | External viewer   |
