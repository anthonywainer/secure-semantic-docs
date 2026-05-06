"""SparkReader: read synthetic_data from batch or streaming Spark sources."""

from __future__ import annotations

from typing import Any

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.readwriter import DataFrameReader
from pyspark.sql.streaming import DataStreamReader


class SparkReader:
    """Utility class to read synthetic_data from Spark sources.

    Provides a unified interface to read from tables, batch files, or
    streaming sources.  Accepts options either as flat keyword arguments or
    as a nested ``options`` dict (matching the YAML reader entry format).

    Usage::

        reader = SparkReader(spark)

        # From a named entry in config
        entry = config.readers["bronze_documents"]
        df = reader.read(stream=entry.stream, **entry.options)

        # Explicit call
        df = reader.read(format="parquet", path="/synthetic_data/bronze", mergeSchema="true")
    """

    def __init__(self, spark: SparkSession) -> None:
        self.spark = spark

    def read(
            self,
            *,
            table_name: str | None = None,
            path: str | None = None,
            stream: bool = False,
            **options: Any
    ) -> DataFrame:
        """Read from *table_name* or *path*.

        Parameters
        ----------
        table_name:
            Fully qualified table name.  Mutually exclusive with *path*.
        path:
            File system path or glob.  Mutually exclusive with *table_name*.
        stream:
            When ``True`` use ``readStream`` instead of ``read``.
        **options:
            Remaining Spark reader options (``format``, ``mergeSchema``, …).
            May include a nested ``options`` dict produced by the YAML loader.
        """
        nested = options.pop("options", None)
        if nested is not None:
            if not isinstance(nested, dict):
                raise TypeError("'options' must be a dict")
            options = {**nested, **options}

        def take(name: str, current: Any) -> Any:
            return current if current is not None else options.pop(name, None)

        path = take("path", path)
        table_name = take("table_name", table_name)

        if table_name is not None and path is not None:
            raise ValueError("Provide either 'table_name' or 'path', not both")

        if table_name:
            return self.table(table_name, stream)
        return self.load(path, stream, **options)

    def _reader(self, stream: bool) -> DataStreamReader | DataFrameReader:
        return self.spark.readStream if stream else self.spark.read

    def table(self, table_name: str, stream: bool = False) -> DataFrame:
        """Read an existing table by name."""
        return self._reader(stream).table(table_name)

    def load(self, path: str | None, stream: bool = False, **options: Any) -> DataFrame:
        """Load synthetic_data from *path* applying *options* to the Spark reader."""
        return self._reader(stream).load(path, **options)
