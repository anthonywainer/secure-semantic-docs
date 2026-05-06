"""DDL-based schema loader for the bronze layer.

Schemas are stored as SQL DDL files under::

    src/secure_semantic_docs/resources/catalog_metadata/<schema>.<table>.ddl

File naming mirrors the Iceberg table layout:

    bronze.documents.ddl   -- bronze layer  (CREATE TABLE bronze.documents)

Callers use the logical name ``"bronze_documents"`` which is translated
to the correct file via :synthetic_data:`_SCHEMA_FILE_MAP`.

Each file is a standard ``CREATE TABLE IF NOT EXISTS`` statement with
column-level ``COMMENT`` annotations and ``TBLPROPERTIES`` metadata.

PySpark's :func:`pyspark.sql.types.StructType.fromDDL` accepts only the
column-definition list (without the ``CREATE TABLE`` wrapper).  This module
extracts that list and returns a :class:`pyspark.sql.types.StructType`.
"""

import re
from pathlib import Path

from pyspark.sql.types import StructType

from secure_semantic_docs.core.logging import get_logger
from secure_semantic_docs.core.settings import BaseSettings

logger = get_logger(BaseSettings.APP_NAME)

_SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "resources" / "catalog_metadata"

_SCHEMA_FILE_MAP: dict[str, str] = {"bronze_documents": "bronze.documents.ddl"}


def _extract_column_defs(ddl_text: str) -> str:
    """Extract the column-definition list from a CREATE TABLE DDL string.

    Strips SQL line comments (``--``), then finds the column block between
    the first ``(`` and its matching ``)`` using a balanced-parenthesis walk,
    so that ``TBLPROPERTIES ( ... )`` at the end of the file and any ``(``
    characters inside comment lines do not confuse the extraction.

    Returns only the comma-separated column definitions suitable for
    :func:`StructType.fromDDL`.
    """
    # Remove SQL line comments so parentheses inside them are ignored.
    stripped = re.sub(r"--[^\n]*", "", ddl_text)

    # Find the first '(' -- opening of the column block.
    start = stripped.index("(") + 1

    # Walk forward tracking depth to find the *matching* closing ')'.
    depth = 1
    pos = start
    while pos < len(stripped) and depth > 0:
        if stripped[pos] == "(":
            depth += 1
        elif stripped[pos] == ")":
            depth -= 1
        pos += 1
    # pos is now one past the matching ')'; column block content is [start:pos-1].
    end = pos - 1

    raw = stripped[start:end]

    # Remove SQL COMMENT clauses (not supported by Spark's fromDDL).
    raw = re.sub(r"\bCOMMENT\s+'[^']*'", "", raw, flags=re.IGNORECASE)
    # Collapse excess whitespace and newlines produced by comment removal.
    return re.sub(r"\s+", " ", raw).strip()


def load_schema(table_name: str) -> StructType:
    """Return the PySpark :class:`StructType` for *table_name*.

    Reads the DDL file mapped from *table_name* in :synthetic_data:`_SCHEMA_FILE_MAP`
    and converts it to a :class:`StructType` via :func:`StructType.fromDDL`.

    Parameters
    ----------
    table_name:
        Logical table key: ``"bronze_documents"``.

    Raises
    ------
    ValueError
        When *table_name* is not a known logical table key.
    FileNotFoundError
        When the resolved DDL file does not exist.
    """
    if table_name not in _SCHEMA_FILE_MAP:
        raise ValueError(
            f"Unknown logical table name '{table_name}'. "
            f"Valid names: {list(_SCHEMA_FILE_MAP)}"
        )
    ddl_filename = _SCHEMA_FILE_MAP[table_name]
    ddl_path = _SCHEMAS_DIR / ddl_filename
    if not ddl_path.exists():
        raise FileNotFoundError(f"DDL schema file not found: {ddl_path}")
    ddl_text = ddl_path.read_text(encoding="utf-8")
    col_defs = _extract_column_defs(ddl_text)
    schema = StructType.fromDDL(col_defs)
    logger.debug(
        "Loaded schema '%s' from %s (%d fields)",
        table_name,
        ddl_filename,
        len(schema.fields)
    )
    return schema
