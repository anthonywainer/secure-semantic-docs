"""Reader configuration dataclasses.

Each named reader entry maps to a YAML block::

    readers:
      my_source:
        stream: false
        options:
          format: csv
          header: "true"
          path: "{env[MY_DIR]}/synthetic_data/my_source.csv"
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReaderEntry:
    """Single named reader entry parsed from YAML.

    Attributes
    ----------
    stream:
        When ``True`` the reader uses ``SparkSession.readStream``.
    options:
        Arbitrary key-value options forwarded to the Spark reader
        (``format``, ``path``, ``mergeSchema``, …).
    """

    stream: bool = False
    options: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ReadersConfig:
    """Mapping of named reader entries loaded from YAML.

    Usage::

        entry = config.readers["bronze_documents"]
        reader = SparkReader(spark)
        df = reader.read(stream=entry.stream, **entry.options)
    """

    entries: dict[str, ReaderEntry] = field(default_factory=dict)

    def get(self, name: str) -> ReaderEntry | None:
        """Return the entry for *name*, or ``None`` if absent."""
        return self.entries.get(name)

    def __getitem__(self, name: str) -> ReaderEntry:
        return self.entries[name]

    def __contains__(self, name: object) -> bool:
        return name in self.entries

    def names(self) -> list[str]:
        """Return all configured reader names."""
        return list(self.entries)
