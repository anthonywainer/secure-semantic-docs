# Trino Configuration

Trino configuration lives at `config/trino/` in the project root.

## Directory structure

```text
config/trino/
├── etc/          # Trino coordinator config (config.properties, jvm.config, etc.)
├── catalog/      # lakehouse.properties — Hive connector over local Parquet files
├── security/     # rules.json (file-based ACL), groups.json
├── init/         # init_tables.sql — creates schemas and safe views
└── metastore/    # File-based Hive metastore directory (bind mounted)
```

## Connector

Trino 406 with the Hive connector and file-based metastore.
Queries Parquet files in `./runtime/lakehouse/` via `file:///data/lakehouse/`.

## Iceberg note

Iceberg REST catalog is a future milestone. Current setup uses Parquet + Hive file metastore.

## Governed views

All user-facing access goes through `lakehouse.safe.*` views.
The `lakehouse.raw.*` schema is admin-only.

See `config/trino/init/init_tables.sql` for view definitions.
