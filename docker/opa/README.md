# OPA Policy Configuration

OPA configuration lives at `config/opa/` in the project root.

## Directory structure

```text
config/opa/
├── policies/
│   └── trino_authz.rego   # Trino authorization policy
└── data/
    ├── users_roles.json    # User → role mapping
    └── table_policies.json # Table access rules per role
```

## Port

OPA runs on port `8181`.

## Integration status

OPA policy files define the intended authorization model.
Trino file-based ACL (`config/trino/security/rules.json`) is the **active** enforcement mechanism.

Full OPA-Trino wiring requires the `trino-opa-authorizer` plugin.
See `docs/trino_opa_superset.md` for integration details.

## Policy

`trino_authz.rego` enforces:

- Per-role schema access (raw = admin only; safe = all roles)
- Per-role table/view access
- Column blocking (embedding_ciphertext, nonce, key_id, etc.)
