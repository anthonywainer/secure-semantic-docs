"""Writer configuration dataclasses.

Each named writer entry maps to a YAML block::

    writers:
      my_sink:
        stream: true
        options:
          format: delta
          table_name: "schema.my_sink"
          path: "{env[MY_DIR]}/synthetic_data/warehouse/my_sink"
          checkpointLocation: "{env[MY_DIR]}/synthetic_data/checkpoints/my_sink"
          mergeSchema: "true"
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WriterEntry:
    """Single named writer entry parsed from YAML.

    Attributes
    ----------
    stream:
        When ``True`` the writer uses ``DataFrame.writeStream``.
    options:
        Arbitrary key-value options forwarded to the Spark writer
        (``format``, ``mode``, ``path``, ``table_name``,
        ``checkpointLocation``, …).
    """

    stream: bool = False
    options: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class WritersConfig:
    """Mapping of named writer entries loaded from YAML.

    Usage::

        entry = config.writers["bronze_documents"]
        writer = SparkWriter(spark)
        writer.write(df, stream=entry.stream, path=str(cfg.bronze_dir), **entry.options)
    """

    entries: dict[str, WriterEntry] = field(default_factory=dict)

    def get(self, name: str) -> WriterEntry | None:
        """Return the entry for *name*, or ``None`` if absent."""
        return self.entries.get(name)

    def __getitem__(self, name: str) -> WriterEntry:
        return self.entries[name]

    def __contains__(self, name: object) -> bool:
        return name in self.entries

    def names(self) -> list[str]:
        """Return all configured writer names."""
        return list(self.entries)
