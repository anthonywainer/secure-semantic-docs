from __future__ import annotations

import json
from pathlib import Path

from pyspark.sql import Row

# noinspection PyProtectedMember
from secure_semantic_docs.processing.fact_extractor import (
    _extract_fact_partition,  # noqa: SLF001
    extract_facts_df,
    extract_facts_df_document_aware,
    extract_facts_from_chunk,
    fact_schema,
    write_facts_jsonl
)


def test_extract_facts_from_chunk_returns_empty_for_missing_text() -> None:
    assert extract_facts_from_chunk({"chunk_text": None}, "2026-01-01T00:00:00Z") == []


def test_extract_facts_df_returns_rows_with_schema(spark) -> None:
    rows = [
        {
            "document_id": "DOC-009",
            "chunk_id": "DOC-009-000",
            "classification": "confidential",
            "allowed_roles": ["security_engineer"],
            "department": "Engineering",
            "source_path": "confidential/DOC-009_incident.txt",
            "chunk_text": (
                "INCIDENT REPORT: PIPELINE OUTAGE 2024-01-15\n"
                "Incident commander: hshaw@example.org"
            )
        },
        {
            "document_id": "DOC-001",
            "chunk_id": "DOC-001-000",
            "classification": "public",
            "allowed_roles": [],
            "department": "Ops",
            "source_path": "public/DOC-001.txt",
            "chunk_text": None
        }
    ]
    chunk_df = spark.createDataFrame(rows)

    fact_df = extract_facts_df(spark, chunk_df, "2026-01-01T00:00:00Z")
    records = [row.asDict(recursive=True) for row in fact_df.collect()]

    assert len(records) == 1
    assert records[0]["fact_type"] == "incident_commander"
    assert fact_df.schema == fact_schema()


def test_extract_facts_df_document_aware_handles_empty_and_combined_text(spark) -> None:
    empty_df = spark.createDataFrame([], schema=(
        "document_id string, chunk_id string, chunk_index int, classification string, "
        "allowed_roles array<string>, department string, source_path string, chunk_text string"
    ))
    empty_result = extract_facts_df_document_aware(spark, empty_df, "2026-01-01T00:00:00Z")
    assert empty_result.collect() == []

    chunk_df = spark.createDataFrame([
        {
            "document_id": "DOC-009",
            "chunk_id": "DOC-009-001",
            "chunk_index": 1,
            "classification": "confidential",
            "allowed_roles": ["security_engineer"],
            "department": "Engineering",
            "source_path": "confidential/DOC-009_incident.txt",
            "chunk_text": "Incident commander: hshaw@example.org"
        },
        {
            "document_id": "DOC-009",
            "chunk_id": "DOC-009-000",
            "chunk_index": 0,
            "classification": "confidential",
            "allowed_roles": ["security_engineer"],
            "department": "Engineering",
            "source_path": "confidential/DOC-009_incident.txt",
            "chunk_text": "INCIDENT REPORT: PIPELINE OUTAGE 2024-01-15"
        }
    ])

    result = extract_facts_df_document_aware(spark, chunk_df, "2026-01-01T00:00:00Z")
    records = [row.asDict(recursive=True) for row in result.collect()]

    assert len(records) == 1
    assert records[0]["chunk_id"] == "DOC-009-001"
    assert records[0]["extraction_method"] == "regex:v1:document_aware"


def test_write_facts_jsonl_and_partition_helper(tmp_path: Path) -> None:
    facts_path = tmp_path / "facts" / "facts.jsonl"
    record = {
        "fact_id": "fact-1",
        "fact_type": "incident_commander",
        "subject": "PIPELINE OUTAGE 2024-01-15",
        "predicate": "HAS_INCIDENT_COMMANDER",
        "object": "hshaw@example.org",
        "document_id": "DOC-009",
        "chunk_id": "DOC-009-001",
        "classification": "confidential",
        "allowed_roles": ["security_engineer"],
        "department": "Engineering",
        "source_path": "confidential/DOC-009_incident.txt",
        "confidence": 0.98,
        "extraction_method": "regex:v1",
        "created_at": "2026-01-01T00:00:00Z"
    }

    write_facts_jsonl([record], facts_path)
    lines = facts_path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == record

    partition_rows = iter([
        Row(
            document_id="DOC-009",
            chunk_id="DOC-009-001",
            classification="confidential",
            allowed_roles=["security_engineer"],
            department="Engineering",
            source_path="confidential/DOC-009_incident.txt",
            chunk_text=(
                "INCIDENT REPORT: PIPELINE OUTAGE 2024-01-15\n"
                "Incident commander: hshaw@example.org"
            )
        )
    ])
    tuples = list(_extract_fact_partition(partition_rows, "2026-01-01T00:00:00Z"))
    assert len(tuples) == 1
    assert tuples[0][0] == "fact-1" or isinstance(tuples[0][0], str)
