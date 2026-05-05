"""Synthetic enterprise dataset generator.

Generates fake documents, metadata, and users for demonstration purposes.
All data is entirely synthetic -- no real credentials, people, or
organisations are included.

Document content templates are stored as plain-text files under::

    resources/templates/<index>_<category_slug>.txt

Each template file uses Python str.format() placeholders for sensitive
values that are substituted at generation time.
"""

import hashlib
import json
import logging
import random
import re
from datetime import datetime, timedelta
from pathlib import Path

from faker import Faker

from secure_semantic_docs.config import Config, load_config

logger = logging.getLogger(__name__)

fake = Faker()
Faker.seed(42)
random.seed(42)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "resources" / "templates"

CLASSIFICATIONS = ["public", "internal", "confidential", "restricted"]

ROLES = [
    "data_engineer",
    "business_analyst",
    "security_engineer",
    "finance_manager",
    "external_viewer",
    "hr_manager",
    "platform_engineer",
    "compliance_officer"
]

# Metadata only -- content is loaded from resources/templates/<index>_*.txt
DOCUMENT_TEMPLATES: list[dict[str, object]] = [
    {
        "title": "Data Platform Engineering Handbook",
        "classification": "internal",
        "department": "Data Platform",
        "allowed_roles": ["data_engineer", "platform_engineer", "business_analyst"],
        "contains_sensitive_info": False,
        "retention_policy": "3_years",
        "category": "handbook"
    },
    {
        "title": "Onboarding Guide for New Data Engineers",
        "classification": "internal",
        "department": "Engineering",
        "allowed_roles": ["data_engineer", "platform_engineer", "hr_manager"],
        "contains_sensitive_info": False,
        "retention_policy": "2_years",
        "category": "onboarding"
    },
    {
        "title": "Data Quality Policy v2",
        "classification": "internal",
        "department": "Data Platform",
        "allowed_roles": [
            "data_engineer",
            "platform_engineer",
            "compliance_officer",
            "business_analyst"
        ],
        "contains_sensitive_info": False,
        "retention_policy": "5_years",
        "category": "policy"
    },
    {
        "title": "Architecture Decision Record: Lakehouse Migration",
        "classification": "internal",
        "department": "Engineering",
        "allowed_roles": [
            "data_engineer",
            "platform_engineer",
            "business_analyst",
            "security_engineer"
        ],
        "contains_sensitive_info": False,
        "retention_policy": "permanent",
        "category": "adr"
    },
    {
        "title": "Open Source Tools Evaluation Summary",
        "classification": "public",
        "department": "Engineering",
        "allowed_roles": ROLES,
        "contains_sensitive_info": False,
        "retention_policy": "2_years",
        "category": "evaluation"
    },
    {
        "title": "Semantic Search Architecture Overview",
        "classification": "public",
        "department": "Data Platform",
        "allowed_roles": ROLES,
        "contains_sensitive_info": False,
        "retention_policy": "2_years",
        "category": "architecture"
    },
    {
        "title": "Compliance Policy: GDPR Data Handling",
        "classification": "internal",
        "department": "Legal",
        "allowed_roles": [
            "compliance_officer",
            "hr_manager",
            "security_engineer",
            "data_engineer"
        ],
        "contains_sensitive_info": True,
        "retention_policy": "7_years",
        "category": "compliance"
    },
    {
        "title": "Security Audit Report: Data Platform Q3",
        "classification": "confidential",
        "department": "Security",
        "allowed_roles": ["security_engineer", "compliance_officer"],
        "contains_sensitive_info": True,
        "retention_policy": "5_years",
        "category": "security_audit"
    },
    {
        "title": "Incident Report: Pipeline Outage 2024-01-15",
        "classification": "confidential",
        "department": "Engineering",
        "allowed_roles": ["data_engineer", "platform_engineer", "security_engineer"],
        "contains_sensitive_info": True,
        "retention_policy": "3_years",
        "category": "incident"
    },
    {
        "title": "Payroll Policy and Exception Handling",
        "classification": "restricted",
        "department": "Finance",
        "allowed_roles": ["finance_manager", "hr_manager"],
        "contains_sensitive_info": True,
        "retention_policy": "7_years",
        "category": "payroll"
    },
    {
        "title": "Client Contract Summary: Strategic Partnership",
        "classification": "restricted",
        "department": "Legal",
        "allowed_roles": ["compliance_officer", "finance_manager"],
        "contains_sensitive_info": True,
        "retention_policy": "10_years",
        "category": "contract"
    },
    {
        "title": "Data Retention Schedule",
        "classification": "internal",
        "department": "Legal",
        "allowed_roles": [
            "compliance_officer",
            "data_engineer",
            "hr_manager",
            "security_engineer"
        ],
        "contains_sensitive_info": False,
        "retention_policy": "permanent",
        "category": "policy"
    },
    {
        "title": "Embedding Model Evaluation Report",
        "classification": "internal",
        "department": "Data Platform",
        "allowed_roles": ["data_engineer", "platform_engineer", "business_analyst"],
        "contains_sensitive_info": False,
        "retention_policy": "2_years",
        "category": "evaluation"
    },
    {
        "title": "Access Control Policy v3",
        "classification": "internal",
        "department": "Security",
        "allowed_roles": ["security_engineer", "compliance_officer", "data_engineer"],
        "contains_sensitive_info": False,
        "retention_policy": "permanent",
        "category": "policy"
    },
    {
        "title": "Vector Database Performance Benchmarks",
        "classification": "internal",
        "department": "Data Platform",
        "allowed_roles": ["data_engineer", "platform_engineer"],
        "contains_sensitive_info": False,
        "retention_policy": "2_years",
        "category": "benchmark"
    },
    {
        "title": "HR Policy: Remote Work Guidelines",
        "classification": "internal",
        "department": "HR",
        "allowed_roles": ROLES,
        "contains_sensitive_info": False,
        "retention_policy": "2_years",
        "category": "hr_policy"
    },
    {
        "title": "Data Platform Runbook: Bronze Layer Ingestion",
        "classification": "internal",
        "department": "Data Platform",
        "allowed_roles": ["data_engineer", "platform_engineer"],
        "contains_sensitive_info": False,
        "retention_policy": "3_years",
        "category": "runbook"
    },
    {
        "title": "Security Policy: Cryptographic Standards",
        "classification": "confidential",
        "department": "Security",
        "allowed_roles": ["security_engineer", "compliance_officer"],
        "contains_sensitive_info": True,
        "retention_policy": "permanent",
        "category": "security_policy"
    },
    {
        "title": "Audit Log Policy and Procedures",
        "classification": "internal",
        "department": "Security",
        "allowed_roles": [
            "security_engineer",
            "compliance_officer",
            "data_engineer",
            "platform_engineer"
        ],
        "contains_sensitive_info": False,
        "retention_policy": "5_years",
        "category": "policy"
    },
    {
        "title": "Finance Report: Q4 Budget Variance",
        "classification": "restricted",
        "department": "Finance",
        "allowed_roles": ["finance_manager"],
        "contains_sensitive_info": True,
        "retention_policy": "7_years",
        "category": "finance"
    },
    {
        "title": "Penetration Test Summary: External Perimeter",
        "classification": "confidential",
        "department": "Security",
        "allowed_roles": ["security_engineer", "compliance_officer"],
        "contains_sensitive_info": True,
        "retention_policy": "5_years",
        "category": "pentest"
    },
    {
        "title": "PySpark Best Practices Guide",
        "classification": "public",
        "department": "Data Platform",
        "allowed_roles": ROLES,
        "contains_sensitive_info": False,
        "retention_policy": "2_years",
        "category": "guide"
    },
    {
        "title": "Information Security Awareness Training",
        "classification": "public",
        "department": "Security",
        "allowed_roles": ROLES,
        "contains_sensitive_info": False,
        "retention_policy": "2_years",
        "category": "training"
    },
    {
        "title": "Platform SLA and Monitoring Standards",
        "classification": "internal",
        "department": "Operations",
        "allowed_roles": [
            "data_engineer",
            "platform_engineer",
            "business_analyst",
            "compliance_officer"
        ],
        "contains_sensitive_info": False,
        "retention_policy": "3_years",
        "category": "sla"
    },
    {
        "title": "Model Governance Policy",
        "classification": "internal",
        "department": "Data Platform",
        "allowed_roles": [
            "data_engineer",
            "platform_engineer",
            "compliance_officer",
            "security_engineer"
        ],
        "contains_sensitive_info": False,
        "retention_policy": "5_years",
        "category": "governance"
    }
]


def _slug(text: str) -> str:
    """Return a lowercase ASCII slug suitable for file names."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")[:60]


def _load_template_content(index: int, title: str) -> str:
    """Load the template file for document *index* from resources/templates/.

    Files are named ``<index:02d>_<title_slug>.txt``.
    Raises :class:`FileNotFoundError` when the file is missing.
    """
    filename = f"{index:02d}_{_slug(title)}.txt"
    path = _TEMPLATES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Template file not found: {path}. "
            "Re-run the template extraction step or check resources/templates/."
        )
    return path.read_text(encoding="utf-8")


def _fake_sensitive_values() -> dict[str, str]:
    """Generate fake sensitive values for document templates."""
    return {
        "email": fake.email(),
        "employee_id": f"EMP-{fake.numerify('######')}",
        "client_id": f"CLT-{fake.bothify('??-#####').upper()}",
        "project_code": f"PROJ-{fake.bothify('???-###').upper()}",
        "financial_amount": f"${fake.numerify('###,###.##')}",
        "fake_token": f"tok_{fake.md5()[:32]}",
        "finding_count": str(random.randint(2, 8))
    }


def _hash_content(content: str) -> str:
    """Hash document content with SHA-256."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _random_date_within_last_two_years() -> str:
    """Return a random ISO timestamp within the last two years."""
    days_ago = random.randint(0, 730)
    dt = datetime.now() - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_documents(config: Config | None = None) -> list[dict[str, object]]:
    """Generate synthetic enterprise documents and write them to disk."""
    cfg = config or load_config()
    documents_metadata: list[dict[str, object]] = []

    for index, template in enumerate(DOCUMENT_TEMPLATES, start=1):
        values = _fake_sensitive_values()
        raw_template = _load_template_content(index, str(template["title"]))
        content = raw_template.format(**values)
        classification = str(template["classification"])
        category = str(template["category"])
        doc_id = f"DOC-{index:03d}"
        subfolder = cfg.raw_documents_dir / classification
        subfolder.mkdir(parents=True, exist_ok=True)
        file_path = subfolder / f"{doc_id}_{category}.txt"
        file_path.write_text(content, encoding="utf-8")

        documents_metadata.append(
            {
                "document_id": doc_id,
                "title": str(template["title"]),
                "source_path": str(file_path.relative_to(cfg.project_root)),
                "classification": classification,
                "owner": fake.name(),
                "department": str(template["department"]),
                "allowed_roles": list(template["allowed_roles"]),
                "version": f"1.{random.randint(0, 5)}",
                "created_at": _random_date_within_last_two_years(),
                "contains_sensitive_info": bool(template["contains_sensitive_info"]),
                "retention_policy": str(template["retention_policy"]),
                "document_hash": _hash_content(content)
            }
        )

    logger.info("Generated %d documents.", len(documents_metadata))
    return documents_metadata


def generate_users() -> list[dict[str, str]]:
    """Generate synthetic enterprise users."""
    users = [
        {
            "user_id": "USR-001",
            "name": "Alice Nguyen",
            "role": "data_engineer",
            "department": "Data Platform",
            "clearance_level": "internal"
        },
        {
            "user_id": "USR-002",
            "name": "Bob Martinez",
            "role": "business_analyst",
            "department": "Operations",
            "clearance_level": "internal"
        },
        {
            "user_id": "USR-003",
            "name": "Carol Smith",
            "role": "security_engineer",
            "department": "Security",
            "clearance_level": "confidential"
        },
        {
            "user_id": "USR-004",
            "name": "David Chen",
            "role": "finance_manager",
            "department": "Finance",
            "clearance_level": "restricted"
        },
        {
            "user_id": "USR-005",
            "name": "Eve Johnson",
            "role": "external_viewer",
            "department": "External",
            "clearance_level": "public"
        }
    ]
    logger.info("Generated %d users.", len(users))
    return users


def save_dataset(config: Config | None = None) -> None:
    """Generate and persist all synthetic data to disk."""
    cfg = config or load_config()
    cfg.metadata_dir.mkdir(parents=True, exist_ok=True)
    cfg.users_dir.mkdir(parents=True, exist_ok=True)

    documents_metadata = generate_documents(cfg)
    metadata_path = cfg.metadata_dir / "documents_metadata.json"
    metadata_path.write_text(json.dumps(documents_metadata, indent=2), encoding="utf-8")
    logger.info("Saved document metadata to %s", metadata_path)

    users = generate_users()
    users_path = cfg.users_dir / "users.json"
    users_path.write_text(json.dumps(users, indent=2), encoding="utf-8")
    logger.info("Saved users to %s", users_path)
