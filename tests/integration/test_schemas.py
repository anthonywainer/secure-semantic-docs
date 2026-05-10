"""Integration tests for DDL-based schema loader.

These tests require a live SparkSession (via the ``spark`` fixture
in conftest.py) since ``StructType.fromDDL()`` needs the JVM.

Run with:
    uv run pytest tests/integration/ -v
"""

import pytest

from secure_semantic_docs.storage.schemas import load_schema


@pytest.mark.integration
class TestLoadSchemaBronze:
    def test_field_names(self, spark):
        fields = load_schema("bronze_documents").fields or []
        field_names = {f.name for f in fields}
        assert {
                   "document_id",
                   "source_path",
                   "classification",
                   "allowed_roles",
                   "ingestion_timestamp"
               } <= field_names

    def test_document_id_not_nullable(self, spark):
        fields = load_schema("bronze_documents").fields or []
        doc_id = next(f for f in fields if f.name == "document_id")
        assert doc_id.nullable is False

    def test_field_count(self, spark):
        assert len(load_schema("bronze_documents").fields or []) == 12

    def test_returns_struct_type(self, spark):
        from pyspark.sql.types import StructType

        assert isinstance(load_schema("bronze_documents"), StructType)
