"""Tests for YAML-driven configuration loading.

Bundled config files (config.yml + config.dev.yml) live inside the package
resources and are always loaded.  Only config.local.yml is read from
*project_root*, making it the sole machine-local override path tested here.
"""

import pytest

from secure_semantic_docs.loader import (
    Config,
    ReaderEntry,
    ReadersConfig,
    SparkConfig,
    WriterEntry,
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
        base = {"spark": {"shuffle_partitions": 4, "driver_memory": "2g"}}
        override = {"spark": {"shuffle_partitions": 8}}
        result = deep_merge(base, override)
        assert result["spark"]["shuffle_partitions"] == 8
        assert result["spark"]["driver_memory"] == "2g"

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
        f.write_text("spark_confs:\n  shuffle_partitions: 8\n")
        result = load_yaml_file(f)
        assert result["spark_confs"]["shuffle_partitions"] == 8

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
    """Bundled resources/config.yml + resources/config.dev.yml are always loaded."""

    def test_bundled_spark_master(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.spark.confs["spark.master"] == "local[*]"

    def test_bundled_spark_shuffle_partitions_dev(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.spark.confs["spark.sql.shuffle.partitions"] == "2"

    def test_bundled_bronze_reader_exists(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert "bronze_documents" in cfg.readers

    def test_bundled_bronze_reader_format(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.readers["bronze_documents"].options["format"] == "parquet"

    def test_bundled_bronze_writer_exists(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert "bronze_documents" in cfg.writers

    def test_bundled_bronze_writer_dev_compression(self, tmp_path):
        """config.dev.yml overrides compression to 'none'."""
        cfg = load_config(project_root=tmp_path)
        assert cfg.writers["bronze_documents"].options["compression"] == "none"


class TestLocalOverride:
    """config.local.yml at project_root overrides bundled settings."""

    def test_local_overrides_spark_partitions(self, tmp_path):
        (tmp_path / "config.local.yml").write_text(
            "spark_confs:\n  spark.sql.shuffle.partitions: 8\n"
        )
        cfg = load_config(project_root=tmp_path)
        assert cfg.spark.confs["spark.sql.shuffle.partitions"] == "8"

    def test_local_adds_new_reader(self, tmp_path):
        (tmp_path / "config.local.yml").write_text(
            "readers:\n  my_source:\n    stream: false\n    options:\n      format: csv\n"
        )
        cfg = load_config(project_root=tmp_path)
        assert "my_source" in cfg.readers
        assert cfg.readers["my_source"].options["format"] == "csv"


class TestConfigPaths:
    def test_project_root_set(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.project_root == tmp_path

    def test_derived_paths_relative_to_root(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.bronze_dir == tmp_path / "lakehouse" / "bronze_documents"
        assert cfg.logs_dir == tmp_path / "logs"


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


class TestEnvExpansion:
    def test_env_placeholder_expanded_in_options(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_DATA_DIR", "/synthetic_data/lake")
        (tmp_path / "config.local.yml").write_text(
            "readers:\n  my_source:\n    options:\n      path: \"{env[MY_DATA_DIR]}/input\"\n"
        )
        cfg = load_config(project_root=tmp_path)
        assert cfg.readers["my_source"].options["path"] == "/synthetic_data/lake/input"

    def test_unknown_env_var_expands_to_empty(self, tmp_path, monkeypatch):
        monkeypatch.delenv("UNKNOWN_VAR", raising=False)
        (tmp_path / "config.local.yml").write_text(
            "readers:\n  src:\n    options:\n      path: \"{env[UNKNOWN_VAR]}/x\"\n"
        )
        cfg = load_config(project_root=tmp_path)
        assert cfg.readers["src"].options["path"] == "/x"


class TestConfigImmutability:
    def test_config_is_frozen(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        with pytest.raises((AttributeError, TypeError)):
            cfg.project_root = tmp_path

    def test_spark_config_is_frozen(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        with pytest.raises((AttributeError, TypeError)):
            cfg.spark.confs = {}

    def test_readers_config_is_frozen(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        with pytest.raises((AttributeError, TypeError)):
            cfg.readers.entries = {}


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

    def test_reader_entry_type(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert isinstance(cfg.readers["bronze_documents"], ReaderEntry)

    def test_writer_entry_type(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert isinstance(cfg.writers["bronze_documents"], WriterEntry)

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
        from secure_semantic_docs.loader import Config

        cfg = Config()
        assert cfg.project_root.is_dir()

    def test_config_no_args_uses_env_var(self, tmp_path, monkeypatch):
        from secure_semantic_docs.loader import Config

        monkeypatch.setenv("DOCSEC_PROJECT_ROOT", str(tmp_path))
        cfg = Config()
        assert cfg.project_root == tmp_path


class TestReadersConfigGet:
    def test_get_returns_entry(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        entry = cfg.readers.get("bronze_documents")
        assert entry is not None
        assert entry.options["format"] == "parquet"

    def test_get_returns_none_for_missing(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.readers.get("nonexistent") is None


class TestWritersConfigGet:
    def test_get_returns_entry(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        entry = cfg.writers.get("bronze_documents")
        assert entry is not None

    def test_get_returns_none_for_missing(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.writers.get("nonexistent") is None


class TestAdditionalPaths:
    def test_data_dir(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.data_dir == tmp_path / "synthetic_data"

    def test_raw_documents_dir(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.raw_documents_dir == tmp_path / "synthetic_data" / "raw_documents"

    def test_metadata_dir(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.metadata_dir == tmp_path / "synthetic_data" / "metadata"

    def test_users_dir(self, tmp_path):
        cfg = load_config(project_root=tmp_path)
        assert cfg.users_dir == tmp_path / "synthetic_data" / "users"
