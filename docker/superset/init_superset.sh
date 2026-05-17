#!/bin/bash
set -e

echo "==> Initialising Superset database..."
superset db upgrade

echo "==> Creating admin user (admin/admin — DEMO ONLY)..."
superset fab create-admin --username admin --firstname Admin --lastname User --email admin@demo.local --password admin || true

echo "==> Running superset init..."
superset init

echo "==> Creating demo users..."
superset fab create-user --role Alpha --username business_analyst --firstname Business --lastname Analyst --email business_analyst@demo.local --password business || true
superset fab create-user --role Alpha --username security_engineer --firstname Security --lastname Engineer --email security_engineer@demo.local --password security || true
superset fab create-user --role Alpha --username finance_manager --firstname Finance --lastname Manager --email finance_manager@demo.local --password finance || true
superset fab create-user --role Gamma --username external_viewer --firstname External --lastname Viewer --email external_viewer@demo.local --password external || true

echo "==> Registering Trino database connection via REST API..."
SUPERSET_URL="http://superset:8088"
TRINO_HOST="${TRINO_HOST:-trino}"
TRINO_PORT="${TRINO_PORT:-8080}"

# Obtain access token
TOKEN=$(curl -sf -X POST "${SUPERSET_URL}/api/v1/security/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin","provider":"db","refresh":true}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

if [ -z "$TOKEN" ]; then
    echo "  ! Could not obtain Superset token — skipping database registration"
    echo "    Add the Trino connection manually at http://localhost:8088/databaseview/add"
    echo "    SQLAlchemy URI: trino://admin@${TRINO_HOST}:${TRINO_PORT}/lakehouse"
else
    curl -sf -X POST "${SUPERSET_URL}/api/v1/database/" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{
            \"database_name\": \"Lakehouse (Trino)\",
            \"sqlalchemy_uri\": \"trino://admin@${TRINO_HOST}:${TRINO_PORT}/lakehouse\",
            \"expose_in_sqllab\": true,
            \"allow_dml\": false,
            \"allow_run_async\": false,
            \"allow_file_upload\": false
        }" > /dev/null && echo "  ✓ Trino database connection registered" \
        || echo "  ! Database may already exist — skipping"
fi

echo "==> Superset initialisation complete."
echo "    Access at http://localhost:8088"
echo "    Credentials: admin/admin (DEMO ONLY — change in production)"
