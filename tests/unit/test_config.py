"""Tests for YAML-driven configuration loading.

Bundled config files (config.yml + config.dev.yml) live inside the package
resources and are always loaded.  Only config.local.yml is read from
*project_root*, making it the sole machine-local override path tested here.
"""

import pytest

from secure_semantic_docs.config import (
    Config,
    ReadersConfig,
    SparkConfig,
    WritersConfig,
    deep_merge,
    load_config,
    load_yaml_file,
)


class TestDeepMerge:
    def test_simple_override(self):
        base = {"a": 1, "b": 2}
        result = deep_merge(base, {"b": 99})
        assert result == {"a": 1, "b": 99}

    def test_nested_override(self):
        base = {"pipeline": {"chunk_size": 400, "chunk_overlap": 80}}
        override = {"pipeline": {"chunk_size": 200}}
        result = deep_merge(base, override)
        assert result["pipeline"]["chunk_size"] == 200
        assert result["pipeline"]["chunk_overlap"] == 80

    def test_does_not_mutate_base(self):
        base = {"a": {"x": 1}}
        deep_merge(base, {"a": {"y": 2}})
        assert "y" not in base["a"]

    def test_new_key_added(self):
        result = deep_merge({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_non_dict_value_overridden(self):
        result = deep_merge({"a": [1, 2]}, {"a": [3, 4]})
        assert result["a"] == [3, 4]


class TestLoadYamlFile:
    def test_missing_file_returns_empty(self, tmp_path):
        result = load_yaml_file(tmp_path / "nonexistent.yml")
        assert result == {}

    def test_valid_file_parsed(self, tmp_path):
        f = tmp_path / "test.yml"
        f.write_text("pipeline:\n  chunk_size: 200\n")
        result = load_yaml_file(f)
        assert result["pipeline"]["chunk_size"] == 200

    def test_empty_file_returns_empty(self, tmp_path):
        f = tmp_path / "empty.yml"
        f.write_text("")
        result = load_yaml_file(f)
        assert result == {}

    def test_non_mapping_returns_empty(self, tmp_path):
        f = tmp_path / "list.yml"
        f.write_text("- item1\n- item2\n")
        result = load_yaml_file(f)
        assert result == {}


class TestLoadConfigBundledDefaults:
    """Bundled resources/config.yml + resources/config.dev.yml are always loaded.

    config.dev.yml sets chunk_size=300 and chroma_collection_name=docsec_dev,
    so those are the effective defaults when no config.local.yml is present.
    """

    def test_bundled_embedding_model(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.embedding_model == "all-MiniLM-L6-v2"

    def test_bundled_dev_chunk_size(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.chunk_size == 300

    def test_bundled_dev_collection(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.chroma_collection_name == "docsec_dev"

    def test_bundled_spark_master(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.spark.master == "local[*]"

    def test_bundled_spark_shuffle_partitions_dev(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        # config.dev.yml overrides shuffle_partitions to 2
        assert cfg.spark.shuffle_partitions == 2

    def test_bundled_parquet_reader_merge_schema(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.readers.parquet.merge_schema is True

    def test_bundled_parquet_writer_dev_compression(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        # config.dev.yml overrides compression to none
        assert cfg.writers.parquet.compression == "none"

    def test_bundled_json_writer_date_format(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.writers.json.date_format == "yyyy-MM-dd"

    def test_bundled_csv_writer_header(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.writers.csv.header is True


class TestLocalOverride:
    """config.local.yml at project_root overrides bundled settings."""

    def test_local_overrides_chunk_size(self, tmp_path):
        (tmp_path / "config.local.yml").write_text("pipeline:\n  chunk_size: 50\n")
        cfg = load_config(project_root=tmp_path)
        assert cfg.chunk_size == 50

    def test_local_overrides_collection(self, tmp_path):
        (tmp_path / "config.local.yml").write_text(
            "storage:\n  chroma_collection_name: local_test\n"
        )
        cfg = load_config(project_root=tmp_path)
        assert cfg.chroma_collection_name == "local_test"

    def test_local_overrides_spark_partitions(self, tmp_path):
        (tmp_path / "config.local.yml").write_text("spark:\n  shuffle_partitions: 8\n")
        cfg = load_config(project_root=tmp_path)
        assert cfg.spark.shuffle_partitions == 8

    def test_local_overrides_writer_compression(self, tmp_path):
        (tmp_path / "config.local.yml").write_text(
            "writers:\n  parquet:\n    compression: gzip\n"
        )
        cfg = load_config(project_root=tmp_path)
        assert cfg.writers.parquet.compression == "gzip"

    def test_local_overrides_embedding_model(self, tmp_path):
        (tmp_path / "config.local.yml").write_text(
            "embedding:\n  model: all-mpnet-base-v2\n"
        )
        cfg = load_config(project_root=tmp_path)
        assert cfg.embedding_model == "all-mpnet-base-v2"


class TestConfigPaths:
    def test_project_root_set(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.project_root == tmp_path

    def test_derived_paths_relative_to_root(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.bronze_dir == tmp_path / "lakehouse" / "bronze_documents"
        assert cfg.silver_dir == tmp_path / "lakehouse" / "silver_chunks"
        assert cfg.gold_dir == tmp_path / "lakehouse" / "gold_embeddings"
        assert cfg.audit_log_path == tmp_path / "logs" / "audit_log.jsonl"

    def test_chroma_dir(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.chroma_dir == tmp_path / "vector_store" / "chroma"

    def test_local_secrets_path(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.local_secrets_path == tmp_path / ".local" / "secrets.json"


class TestEnvVarOverride:
    def test_docsec_env_var_overrides_root(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        cfg = load_config()
        assert cfg.project_root == tmp_path

    def test_legacy_ssd_env_var_also_works(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SSD_PROJECT_ROOT", str(tmp_path))
        cfg = load_config()
        assert cfg.project_root == tmp_path

    def test_explicit_root_wins_over_env_var(
        self, tmp_path, monkeypatch, tmp_path_factory
    ):
        other = tmp_path_factory.mktemp("other")
        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(other))
        cfg = load_config(project_root=tmp_path)
        assert cfg.project_root == tmp_path


class TestConfigImmutability:
    def test_config_is_frozen(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        with pytest.raises((AttributeError, TypeError)):
            cfg.project_root = tmp_path

    def test_spark_config_is_frozen(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        with pytest.raises((AttributeError, TypeError)):
            cfg.spark.master = "local[4]"

    def test_readers_config_is_frozen(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        with pytest.raises((AttributeError, TypeError)):
            cfg.readers.parquet.merge_schema = False


class TestSubConfigTypes:
    def test_spark_config_type(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert isinstance(cfg.spark, SparkConfig)

    def test_readers_config_type(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert isinstance(cfg.readers, ReadersConfig)

    def test_writers_config_type(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert isinstance(cfg.writers, WritersConfig)

    def test_config_type(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert isinstance(cfg, Config)


class TestProdEnv:
    def test_prod_env_loads_iceberg(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DOCSEC_ENV", "prod")
        cfg = load_config(project_root=tmp_path)
        assert cfg.iceberg.enabled is True

    def test_non_prod_env_iceberg_disabled(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DOCSEC_ENV", raising=False)
        cfg = load_config(project_root=tmp_path)
        assert cfg.iceberg.enabled is False


class TestConfigDefaultFactory:
    def test_config_no_args_resolves_project_root(self):
        from secure_semantic_docs.config._schema import Config

        cfg = Config()
        assert cfg.project_root.is_dir()


class TestAdditionalPaths:
    def test_data_dir(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.data_dir == tmp_path / "data"

    def test_raw_documents_dir(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.raw_documents_dir == tmp_path / "data" / "raw_documents"

    def test_metadata_dir(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.metadata_dir == tmp_path / "data" / "metadata"

    def test_users_dir(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.users_dir == tmp_path / "data" / "users"

    def test_openmetadata_assets_path(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.openmetadata_assets_path == (
            tmp_path / "metadata" / "openmetadata_assets.json"
        )


class TestScalarShims:
    def test_embedding_dim(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.embedding_dim == 384

    def test_chunk_overlap(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.chunk_overlap == 80

    def test_default_top_k_dev(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.default_top_k == 3

    def test_retrieval_candidate_multiplier(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.retrieval_candidate_multiplier == 4

    def test_secret_key_env_var(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.secret_key_env_var == "DOCSEC_SECRET_KEY"
