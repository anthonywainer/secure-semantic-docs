"""Tests for DDL-based schema loader -- pure Python, no Spark needed.

Tests that require a live SparkSession are in
``tests/integration/test_schemas.py``.
"""

import pytest

from secure_semantic_docs.storage.schemas import extract_column_defs, load_schema


class TestExtractColumnDefs:
    def test_extracts_between_parens(self):
        ddl = "CREATE TABLE t (\n    id STRING NOT NULL,\n    name STRING\n);"
        result = extract_column_defs(ddl)
        assert "id STRING NOT NULL" in result
        assert "name STRING" in result

    def test_removes_comment_clauses(self):
        ddl = "CREATE TABLE t (\n    id STRING COMMENT 'Primary key'\n);"
        result = extract_column_defs(ddl)
        assert "COMMENT" not in result
        assert "id STRING" in result

    def test_strips_whitespace(self):
        ddl = "CREATE TABLE t (\n    col STRING\n);"
        result = extract_column_defs(ddl)
        assert result == result.strip()

    def test_not_null_preserved(self):
        ddl = "CREATE TABLE t (\n    id STRING NOT NULL\n);"
        assert "NOT NULL" in extract_column_defs(ddl)

    def test_array_type_preserved(self):
        ddl = "CREATE TABLE t (\n    roles ARRAY<STRING>\n);"
        assert "ARRAY<STRING>" in extract_column_defs(ddl)

    def test_multiple_columns(self):
        ddl = "CREATE TABLE t (\n    a STRING,\n    b INT,\n    c BOOLEAN\n);"
        result = extract_column_defs(ddl)
        assert "a STRING" in result
        assert "b INT" in result
        assert "c BOOLEAN" in result

    def test_float_type_preserved(self):
        ddl = "CREATE TABLE t (\n    score FLOAT\n);"
        assert "score FLOAT" in extract_column_defs(ddl)

    def test_unknown_table_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError, match="DDL schema file not found"):
            load_schema("nonexistent_table")

    def test_missing_ddl_file_raises_file_not_found(self, tmp_path, monkeypatch):
        """Covers the branch where the DDL file path does not exist on disk."""
        from secure_semantic_docs.storage import schemas as schemas_mod

        monkeypatch.setattr(
            schemas_mod, "_SCHEMAS_DIR", tmp_path / "schemas_do_not_exist"
        )
        with pytest.raises(FileNotFoundError, match="DDL schema file not found"):
            load_schema("bronze_documents")
