# Trino Authorization Policy
# This policy enforces role-based access control for Trino queries.
# Currently implemented as documentation for future OPA-Trino integration.
# Trino file-based ACL in config/trino/security/rules.json is the active enforcement.
# See docs/trino_opa_superset.md for OPA-Trino wiring details.

package trino.authz

import rego.v1

# Columns that must never be exposed to any user including admin via UI
blocked_columns := {
    "embedding_ciphertext",
    "embedding_nonce",
    "key_id",
    "decrypted_embedding",
    "password",
    "secret"
}

# Schemas accessible per role
accessible_schemas := {
    "admin": {"raw", "safe"},
    "security_engineer": {"safe"},
    "finance_manager": {"safe"},
    "business_analyst": {"safe"},
    "data_engineer": {"safe"},
    "external_viewer": {"safe"}
}

# Tables/views accessible per role within safe schema
accessible_tables := {
    "external_viewer": {
        "v_public_chunks"
    },
    "business_analyst": {
        "bronze_documents",
        "silver_chunks",
        "gold_embedding_catalog",
        "v_bronze_documents_catalog",
        "v_silver_chunks_catalog",
        "v_gold_embedding_catalog",
        "v_public_chunks",
        "v_internal_chunks"
    },
    "data_engineer": {
        "bronze_documents",
        "silver_chunks",
        "gold_embedding_catalog",
        "v_bronze_documents_catalog",
        "v_silver_chunks_catalog",
        "v_gold_embedding_catalog",
        "v_public_chunks",
        "v_internal_chunks"
    },
    "security_engineer": {
        "bronze_documents",
        "silver_chunks",
        "gold_embedding_catalog",
        "v_bronze_documents_catalog",
        "v_silver_chunks_catalog",
        "v_gold_embedding_catalog",
        "v_public_chunks",
        "v_internal_chunks"
    },
    "finance_manager": {
        "bronze_documents",
        "silver_chunks",
        "gold_embedding_catalog",
        "v_bronze_documents_catalog",
        "v_silver_chunks_catalog",
        "v_gold_embedding_catalog",
        "v_public_chunks",
        "v_internal_chunks"
    },
    "admin": {
        "bronze_documents",
        "silver_chunks",
        "gold_embeddings",
        "gold_embedding_catalog",
        "v_bronze_documents_catalog",
        "v_silver_chunks_catalog",
        "v_gold_embedding_catalog",
        "v_public_chunks",
        "v_internal_chunks",
        "v_audit_events"
    }
}

default allow := false

# Allow access if user role grants schema + table access
allow if {
    input.action.operation == "SelectFromColumns"
    role := data.users_roles[input.context.identity.user]
    schemas := accessible_schemas[role]
    input.action.resource.table.schemaName in schemas
    tables := accessible_tables[role]
    input.action.resource.table.tableName in tables
    not column_blocked
}

# Block access to sensitive columns
column_blocked if {
    col := input.action.resource.column.columnName
    col in blocked_columns
}
