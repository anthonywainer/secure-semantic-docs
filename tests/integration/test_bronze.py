"""Integration tests for the bronze ingestion pipeline."""

import pytest

from secure_semantic_docs.config import load_config
from secure_semantic_docs.exceptions import IngestionError
from secure_semantic_docs.pipeline.bronze import (
    _load_metadata,
    _read_raw_text,
    ingest_documents,
    read_bronze,
)
from secure_semantic_docs.synthetic import save_dataset


@pytest.mark.integration
class TestLoadMetadata:
    def test_raises_when_metadata_missing(self, config):
        with pytest.raises(IngestionError, match="Metadata file not found"):
            _load_metadata(config)

    def test_loads_metadata_after_save_dataset(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        save_dataset(cfg)
        metadata = _load_metadata(cfg)
        assert len(metadata) == 25
        for doc_id, record in metadata.items():
            assert doc_id == record["document_id"]


@pytest.mark.integration
class TestReadRawText:
    def test_returns_empty_string_for_missing_file(self, tmp_path):
        result = _read_raw_text("data/raw_documents/missing.txt", tmp_path)
        assert result == ""

    def test_reads_existing_file(self, tmp_path):
        path = tmp_path / "data" / "raw_documents" / "doc.txt"
        path.parent.mkdir(parents=True)
        path.write_text("hello world", encoding="utf-8")
        result = _read_raw_text("data/raw_documents/doc.txt", tmp_path)
        assert result == "hello world"


@pytest.mark.integration
class TestIngestDocuments:
    def test_raises_when_no_metadata(self, spark, config):
        with pytest.raises(IngestionError, match="Metadata file not found"):
            ingest_documents(spark, config)

    def test_ingests_25_documents(self, spark, tmp_path):
        cfg = load_config(project_root=tmp_path)
        save_dataset(cfg)
        ingest_documents(spark, cfg)
        bronze_df = read_bronze(spark, cfg)
        assert bronze_df.count() == 25

    def test_bronze_schema_has_expected_fields(self, spark, tmp_path):
        cfg = load_config(project_root=tmp_path)
        save_dataset(cfg)
        ingest_documents(spark, cfg)
        df = read_bronze(spark, cfg)
        field_names = {f.name for f in df.schema}
        required = {
            "document_id",
            "title",
            "source_path",
            "raw_text",
            "classification",
            "owner",
            "department",
            "allowed_roles",
            "version",
            "created_at",
            "contains_sensitive_info",
            "document_hash",
            "ingestion_timestamp",
        }
        assert required <= field_names

    def test_uses_load_config_when_none(self, spark, monkeypatch, tmp_path):
        cfg = load_config(project_root=tmp_path)
        save_dataset(cfg)
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        ingest_documents(spark)
        df = read_bronze(spark, cfg)
        assert df.count() == 25

    def test_ingestion_timestamp_populated(self, spark, tmp_path):
        cfg = load_config(project_root=tmp_path)
        save_dataset(cfg)
        ingest_documents(spark, cfg)
        df = read_bronze(spark, cfg)
        row = df.first()
        assert row["ingestion_timestamp"] is not None
        assert "T" in row["ingestion_timestamp"]

    def test_raises_when_metadata_is_empty(self, spark, tmp_path):
        cfg = load_config(project_root=tmp_path)
        cfg.metadata_dir.mkdir(parents=True, exist_ok=True)
        (cfg.metadata_dir / "documents_metadata.json").write_text(
            "[]", encoding="utf-8"
        )
        with pytest.raises(IngestionError, match="No documents found to ingest"):
            ingest_documents(spark, cfg)


@pytest.mark.integration
class TestReadBronze:
    def test_raises_when_bronze_not_written(self, spark, config):
        with pytest.raises(IngestionError, match="Bronze"):
            read_bronze(spark, config)

    def test_returns_dataframe(self, spark, tmp_path):
        cfg = load_config(project_root=tmp_path)
        save_dataset(cfg)
        ingest_documents(spark, cfg)
        df = read_bronze(spark, cfg)
        assert df is not None

    def test_uses_load_config_when_none(self, spark, monkeypatch, tmp_path):
        cfg = load_config(project_root=tmp_path)
        save_dataset(cfg)
        ingest_documents(spark, cfg)
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        df = read_bronze(spark)
        assert df.count() == 25
