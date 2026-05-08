"""DDL-based schema loader for the bronze layer.

Schemas are stored as SQL DDL files under::

    src/secure_semantic_docs/resources/catalog_metadata/<schema>.<table>.ddl

File naming mirrors the Iceberg table layout:

    bronze_documents.ddl   -- bronze layer  (CREATE TABLE bronze.documents)

Callers use the logical name ``"bronze_documents"`` which is translated
to the correct file via :synthetic_data:`_SCHEMA_FILE_MAP`.

Each file is a standard ``CREATE TABLE IF NOT EXISTS`` statement with
column-level ``COMMENT`` annotations and ``TBLPROPERTIES`` metadata.

PySpark's :func:`pyspark.sql.types.StructType.fromDDL` accepts only the
column-definition list (without the ``CREATE TABLE`` wrapper).  This module
extracts that list and returns a :class:`pyspark.sql.types.StructType`.
"""

import re

from pyspark.sql.types import StructType

from secure_semantic_docs.core.logging import get_logger
from secure_semantic_docs.core.settings import BaseSettings

logger = get_logger(BaseSettings.APP_NAME)

_SCHEMAS_DIR = BaseSettings.resources_dir / "catalog_metadata"

_RE_SQL_COMMENTS: re.Pattern[str] = re.compile(r"--[^\n]*")
_RE_COMMENT_CLAUSE: re.Pattern[str] = re.compile(r"\bCOMMENT\s+'[^']*'", re.IGNORECASE)
_RE_EXCESS_WHITESPACE: re.Pattern[str] = re.compile(r"\s+")


def extract_column_defs(ddl_text: str) -> str:
    """Extract the column-definition list from a CREATE TABLE DDL string.

    Strips SQL line comments (``--``), then finds the column block between
    the first ``(`` and its matching ``)`` using a balanced-parenthesis walk,
    so that ``TBLPROPERTIES ( ... )`` at the end of the file and any ``(``
    characters inside comment lines do not confuse the extraction.

    Returns only the comma-separated column definitions suitable for
    :func:`StructType.fromDDL`.
    """
    stripped = _RE_SQL_COMMENTS.sub("", ddl_text)

    start = stripped.index("(") + 1

    depth = 1
    pos = start
    while pos < len(stripped) and depth > 0:
        if stripped[pos] == "(":
            depth += 1
        elif stripped[pos] == ")":
            depth -= 1
        pos += 1
    end = pos - 1

    return _RE_EXCESS_WHITESPACE.sub(
        " ",
        _RE_COMMENT_CLAUSE.sub("", stripped[start:end])
    ).strip()


def load_schema(table_name: str) -> StructType:
    """Return the PySpark :class:`StructType` for *table_name*.

    Reads the DDL file at ``<_SCHEMAS_DIR>/<table_name>.ddl``
    and converts it to a :class:`StructType` via :func:`StructType.fromDDL`.

    Parameters
    ----------
    table_name:
        Logical table key, e.g. ``"bronze_documents"`` or ``"silver_chunks"``.

    Raises
    ------
    FileNotFoundError
        When the resolved DDL file does not exist.
    """
    ddl_path = _SCHEMAS_DIR / f"{table_name}.ddl"
    if not ddl_path.exists():
        raise FileNotFoundError(f"DDL schema file not found: {ddl_path}")
    schema = StructType.fromDDL(extract_column_defs(ddl_path.read_text(encoding="utf-8")))
    logger.debug("Loaded schema '%s'  (%d fields)", table_name, len(schema.fields or []))
    return schema
