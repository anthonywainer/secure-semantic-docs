"""Tests for synthetic data generator."""

import json

import pytest

from secure_semantic_docs.config import load_config
from secure_semantic_docs.synthetic import (
    generate_documents,
    generate_users,
    save_dataset,
)


class TestGenerateUsers:
    def test_returns_list(self):
        users = generate_users()
        assert isinstance(users, list)

    def test_returns_five_users(self):
        users = generate_users()
        assert len(users) == 5

    def test_user_has_required_fields(self):
        required = {"user_id", "name", "role", "department", "clearance_level"}
        for user in generate_users():
            assert required <= set(user.keys())

    def test_user_ids_unique(self):
        ids = [u["user_id"] for u in generate_users()]
        assert len(ids) == len(set(ids))

    def test_clearance_levels_valid(self):
        valid = {"public", "internal", "confidential", "restricted"}
        for user in generate_users():
            assert user["clearance_level"] in valid


class TestGenerateDocuments:
    def test_returns_list(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        docs = generate_documents(cfg)
        assert isinstance(docs, list)

    def test_returns_25_documents(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        docs = generate_documents(cfg)
        assert len(docs) == 25

    def test_document_has_required_fields(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        required = {
            "document_id",
            "title",
            "source_path",
            "classification",
            "owner",
            "department",
            "allowed_roles",
            "version",
            "created_at",
            "contains_sensitive_info",
            "retention_policy",
            "document_hash",
        }
        for doc in generate_documents(cfg):
            assert required <= set(doc.keys()), (
                f"Missing fields in {doc['document_id']}"
            )

    def test_document_ids_unique(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        ids = [d["document_id"] for d in generate_documents(cfg)]
        assert len(ids) == len(set(ids))

    def test_classifications_valid(self, tmp_path):
        valid = {"public", "internal", "confidential", "restricted"}
        cfg = load_config(project_root=tmp_path)
        for doc in generate_documents(cfg):
            assert doc["classification"] in valid

    def test_files_written_to_disk(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        generate_documents(cfg)
        assert any(cfg.raw_documents_dir.rglob("*.txt"))

    def test_document_hash_non_empty(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        for doc in generate_documents(cfg):
            assert doc["document_hash"]

    def test_uses_load_config_when_none(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        docs = generate_documents()
        assert len(docs) == 25

    def test_missing_template_raises_file_not_found(self, tmp_path, monkeypatch):
        """Covers the branch where a template file is missing from disk."""
        import secure_semantic_docs.synthetic.generator as gen_mod

        monkeypatch.setattr(gen_mod, "_TEMPLATES_DIR", tmp_path / "no_templates")
        with pytest.raises(FileNotFoundError, match="Template file not found"):
            gen_mod._load_template_content(1, "Some Title")


class TestSaveDataset:
    def test_creates_metadata_file(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        save_dataset(cfg)
        assert (cfg.metadata_dir / "documents_metadata.json").exists()

    def test_creates_users_file(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        save_dataset(cfg)
        assert (cfg.users_dir / "users.json").exists()

    def test_metadata_is_valid_json(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        save_dataset(cfg)
        data = json.loads((cfg.metadata_dir / "documents_metadata.json").read_text())
        assert isinstance(data, list)
        assert len(data) == 25

    def test_users_is_valid_json(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        save_dataset(cfg)
        users = json.loads((cfg.users_dir / "users.json").read_text())
        assert isinstance(users, list)
        assert len(users) == 5

    def test_uses_load_config_when_none(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        save_dataset()
        cfg = load_config(project_root=tmp_path)
        assert (cfg.metadata_dir / "documents_metadata.json").exists()
