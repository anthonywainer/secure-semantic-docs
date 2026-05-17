"""Superset configuration for secure-semantic-docs demo.

WARNING: This configuration uses demo credentials.
Do not use in production without changing all secrets.
"""

import os

SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "demo_superset_secret_key_not_for_production")

SQLALCHEMY_DATABASE_URI = os.environ.get(
    "SQLALCHEMY_DATABASE_URI",
    "postgresql://superset:superset_demo_pass@superset-db:5432/superset"
)

TRINO_HOST = os.environ.get("TRINO_HOST", "trino")
TRINO_PORT = int(os.environ.get("TRINO_PORT", "8080"))

WTF_CSRF_ENABLED = False  # DEMO ONLY — enable and configure properly in production
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
ENABLE_ROW_LEVEL_SECURITY = True

FEATURE_FLAGS: dict[str, bool] = {
    "ENABLE_TEMPLATE_PROCESSING": False,
    "SQLLAB_BACKEND_PERSISTENCE": True
}

PREVENT_UNSAFE_DEFAULT_URLS_ON_DATASET = True
