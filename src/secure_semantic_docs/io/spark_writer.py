"""SparkWriter: write DataFrames to batch or streaming Spark sinks."""

from __future__ import annotations

from typing import Any

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.streaming import StreamingQuery


class SparkWriter:
    """Utility class to write DataFrames to Spark sinks.

    Mirrors :class:`SparkReader` in API style: accepts options either as flat
    keyword arguments or as a nested ``options`` dict (matching the YAML
    writer entry format).

    Usage::

        writer = SparkWriter(spark)

        # From a named entry in config
        entry = config.writers["bronze_documents"]
        writer.write(df, stream=entry.stream, path="/lakehouse/bronze", **entry.options)

        # Explicit call
        writer.write(df, format="parquet", mode="overwrite", path="/synthetic_data/out")
    """

    def __init__(self, spark: SparkSession) -> None:
        self.spark = spark

    def write(
            self,
            df: DataFrame,
            *,
            stream: bool = False,
            table_name: str | None = None,
            path: str | None = None,
            **options: Any
    ) -> StreamingQuery | None:
        """Write *df* to *table_name* or *path*.

        Parameters
        ----------
        df:
            DataFrame to write.
        stream:
            When ``True`` use ``writeStream`` instead of ``write``.
        table_name:
            Destination table name.  Mutually exclusive with *path*.
        path:
            Destination file system path.  Mutually exclusive with *table_name*.
        **options:
            Remaining Spark writer options (``format``, ``mode``,
            ``compression``, ``checkpointLocation``, …).
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
            return self.save_table(df, table_name, stream=stream, **options)
        return self.save(df, path, stream=stream, **options)

    @staticmethod
    def save(
            df: DataFrame,
            path: str | None,
            stream: bool = False,
            **options: Any
    ) -> StreamingQuery | None:
        """Write *df* to *path*.

        Parameters
        ----------
        df:
            DataFrame to write.
        path:
            Destination path.
        stream:
            Use ``writeStream`` when ``True``.
        **options:
            Spark writer options including ``format`` and ``mode``.
        """
        fmt = options.pop("format", None)
        if stream:
            mode = options.pop("mode", "append")
            writer = df.writeStream
            if fmt:
                writer = writer.format(fmt)
            writer = writer.outputMode(mode).options(**options)
            return writer.start(path)

        mode = options.pop("mode", "overwrite")
        writer = df.write
        if fmt:
            writer = writer.format(fmt)
        writer = writer.mode(mode).options(**options)
        writer.save(path)
        return None

    @staticmethod
    def save_table(
            df: DataFrame,
            table_name: str,
            stream: bool = False,
            **options: Any
    ) -> StreamingQuery | None:
        """Write *df* to an existing or new table.

        Parameters
        ----------
        df:
            DataFrame to write.
        table_name:
            Destination table name.
        stream:
            Use ``writeStream`` when ``True``.
        **options:
            Spark writer options including ``format`` and ``mode``.
        """
        fmt = options.pop("format", None)
        if stream:
            mode = options.pop("mode", "append")
            writer = df.writeStream
            if fmt:
                writer = writer.format(fmt)
            writer = writer.outputMode(mode).options(**options)
            return writer.toTable(table_name)

        mode = options.pop("mode", "overwrite")
        writer = df.write
        if fmt:
            writer = writer.format(fmt)

        writer = writer.mode(mode).options(**options)
        writer.saveAsTable(table_name)
        return None
