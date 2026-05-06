"""Integration tests for the bronze ingestion pipeline."""

import pytest

from secure_semantic_docs.bronze_ingestion import ingest
from secure_semantic_docs.io import SparkReader
from secure_semantic_docs.loader import load_config


def _read_bronze(spark, cfg):
    entry = cfg.readers["bronze_documents"]
    return SparkReader(spark).read(stream=entry.stream, **entry.options)


@pytest.mark.integration
class TestIngest:
    def test_ingests_25_documents(self, spark, tmp_path, monkeypatch):
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        cfg = load_config(project_root=tmp_path)
        ingest(spark, cfg)
        assert _read_bronze(spark, cfg).count() == 25

    def test_bronze_schema_has_expected_fields(self, spark, tmp_path, monkeypatch):
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        cfg = load_config(project_root=tmp_path)
        ingest(spark, cfg)
        field_names = {f.name for f in _read_bronze(spark, cfg).schema}
        required = {
            "document_id", "title", "source_path", "raw_text",
            "classification", "owner", "department", "allowed_roles",
            "version", "created_at", "contains_sensitive_info",
            "document_hash", "ingestion_timestamp"
        }
        assert required <= field_names

    def test_ingestion_timestamp_populated(self, spark, tmp_path, monkeypatch):
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        cfg = load_config(project_root=tmp_path)
        ingest(spark, cfg)
        row = _read_bronze(spark, cfg).first()
        assert row["ingestion_timestamp"] is not None
        assert "T" in row["ingestion_timestamp"]
