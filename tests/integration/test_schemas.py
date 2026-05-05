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
        field_names = {f.name for f in load_schema("bronze_documents").fields}
        assert {
            "document_id",
            "raw_text",
            "classification",
            "allowed_roles",
            "ingestion_timestamp"
        } <= field_names

    def test_document_id_not_nullable(self, spark):
        doc_id = next(
            f for f in load_schema("bronze_documents").fields if f.name == "document_id"
        )
        assert doc_id.nullable is False

    def test_field_count(self, spark):
        assert len(load_schema("bronze_documents").fields) == 13

    def test_returns_struct_type(self, spark):
        from pyspark.sql.types import StructType

        assert isinstance(load_schema("bronze_documents"), StructType)


@pytest.mark.integration
class TestLoadSchemaSilver:
    def test_field_names(self, spark):
        field_names = {f.name for f in load_schema("silver_chunks").fields}
        assert {
            "chunk_id",
            "chunk_text",
            "sensitivity_score",
            "requires_encryption",
            "detected_sensitive_types"
        } <= field_names

    def test_chunk_id_not_nullable(self, spark):
        chunk_id = next(
            f for f in load_schema("silver_chunks").fields if f.name == "chunk_id"
        )
        assert chunk_id.nullable is False

    def test_field_count(self, spark):
        assert len(load_schema("silver_chunks").fields) == 15


@pytest.mark.integration
class TestLoadSchemaGold:
    def test_field_names(self, spark):
        field_names = {f.name for f in load_schema("gold_embeddings").fields}
        assert {
            "chunk_id",
            "embedding",
            "embedding_model",
            "sensitivity_score"
        } <= field_names

    def test_chunk_id_not_nullable(self, spark):
        chunk_id = next(
            f for f in load_schema("gold_embeddings").fields if f.name == "chunk_id"
        )
        assert chunk_id.nullable is False

    def test_field_count(self, spark):
        assert len(load_schema("gold_embeddings").fields) == 13
