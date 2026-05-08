"""Integration tests for the silver ingestion pipeline."""

import pytest

from secure_semantic_docs.bronze_ingestion import ingest as bronze_ingest
from secure_semantic_docs.silver_ingestion import ingest
from secure_semantic_docs.io import SparkReader
from secure_semantic_docs.loader import load_config


def _read_silver_chunks(spark, pipeline_config):
    silver_reader_entry = pipeline_config.readers["silver_chunks"]
    return SparkReader(spark).read(
        stream=silver_reader_entry.stream, **silver_reader_entry.options
    )


@pytest.mark.integration
class TestSilverIngest:
    def test_ingest_produces_chunks(self, spark, tmp_path, monkeypatch):
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        pipeline_config = load_config(project_root=tmp_path)
        bronze_ingest(spark, pipeline_config)
        ingest(spark, pipeline_config)
        assert _read_silver_chunks(spark, pipeline_config).count() > 0

    def test_silver_schema_has_expected_fields(self, spark, tmp_path, monkeypatch):
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        pipeline_config = load_config(project_root=tmp_path)
        bronze_ingest(spark, pipeline_config)
        ingest(spark, pipeline_config)
        silver_field_names = {
            schema_field.name
            for schema_field in _read_silver_chunks(spark, pipeline_config).schema
        }
        required_silver_fields = {
            "chunk_id", "document_id", "chunk_index", "chunk_text",
            "classification", "allowed_roles", "owner", "department",
            "version", "source_path", "document_hash"
        }
        assert required_silver_fields <= silver_field_names

    def test_silver_chunks_have_document_ids(self, spark, tmp_path, monkeypatch):
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        pipeline_config = load_config(project_root=tmp_path)
        bronze_ingest(spark, pipeline_config)
        ingest(spark, pipeline_config)
        silver_chunk_row = _read_silver_chunks(spark, pipeline_config).first()
        assert silver_chunk_row is not None
        assert silver_chunk_row["document_id"] is not None
        assert silver_chunk_row["chunk_id"] is not None
