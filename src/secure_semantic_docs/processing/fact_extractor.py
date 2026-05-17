"""Extract governed structured facts from transient chunk text."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pyspark.sql import DataFrame, Row, SparkSession
from pyspark.sql.types import (
    ArrayType,
    DoubleType,
    StringType,
    StructField,
    StructType
)

_INCIDENT_TITLE_PATTERN = re.compile(
    r"INCIDENT\s+REPORT:\s*(?P<title>[^\n=]+?)(?:\s*={3,}|\s*\n|\s*$)",
    re.IGNORECASE
)
_INCIDENT_COMMANDER_PATTERN = re.compile(
    r"Incident\s+commander:\s*(?P<commander>\S+@\S+)",
    re.IGNORECASE
)


@dataclass(frozen=True)
class ExtractedFact:
    """A governed fact persisted without raw source text."""

    fact_id: str
    fact_type: str
    subject: str
    predicate: str
    object: str
    document_id: str
    chunk_id: str
    classification: str
    allowed_roles: list[str]
    department: str
    source_path: str
    confidence: float
    extraction_method: str
    created_at: str

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serializable record."""
        return asdict(self)


def extract_facts_from_chunk(
        chunk: Mapping[str, Any],
        created_at: str
) -> list[dict[str, Any]]:
    """Extract structured facts from one transient chunk record."""
    chunk_text = chunk.get("chunk_text")
    if not isinstance(chunk_text, str) or not chunk_text:
        return []

    title = _extract_incident_title(chunk_text)
    commander = _extract_incident_commander(chunk_text)
    if not title or not commander:
        return []

    fact = ExtractedFact(
        fact_id=_fact_id(chunk, title, "incident_commander"),
        fact_type="incident_commander",
        subject=title,
        predicate="HAS_INCIDENT_COMMANDER",
        object=commander,
        document_id=str(chunk.get("document_id", "")),
        chunk_id=str(chunk.get("chunk_id", "")),
        classification=str(chunk.get("classification", "")),
        allowed_roles=list(chunk.get("allowed_roles") or []),
        department=str(chunk.get("department", "")),
        source_path=str(chunk.get("source_path", "")),
        confidence=0.98,
        extraction_method="regex:v1",
        created_at=created_at
    )
    return [fact.to_record()]


def extract_facts_df(
        spark: SparkSession,
        chunk_workset_df: DataFrame,
        created_at: str
) -> DataFrame:
    """Return extracted facts from a transient chunk workset DataFrame.

    Each chunk is evaluated independently. When facts may span multiple
    chunks (e.g. incident title in one chunk, commander in another), prefer
    :func:`extract_facts_df_document_aware` instead.
    """
    facts_rdd = chunk_workset_df.rdd.mapPartitions(
        lambda rows: _extract_fact_partition(rows, created_at)
    )
    return spark.createDataFrame(facts_rdd, schema=fact_schema())


def extract_facts_df_document_aware(
        spark: SparkSession,
        chunk_workset_df: DataFrame,
        created_at: str
) -> DataFrame:
    """Return extracted facts using full-document text reconstruction.

    Groups all chunks for each ``document_id`` (ordered by ``chunk_index``),
    concatenates their transient ``chunk_text``, then runs pattern extraction
    on the combined text. This allows extraction of facts whose components
    (e.g. incident title and commander) appear in different chunks.

    The ``chunk_id`` stored on each fact prefers the chunk containing the
    matched commander line; if that chunk cannot be identified, the first
    chunk for the document is used as the source reference.

    No plaintext is persisted — this function operates only on the transient
    ``chunk_text`` column that is never written to storage.

    The grouping is performed in Python after a bounded ``collect()`` because
    fact extraction produces at most one record per document and grouping on
    ArrayType columns in Spark SQL is unreliable.
    """
    from collections import defaultdict  # noqa: PLC0415

    rows = (
        chunk_workset_df
        .select(
            "document_id", "chunk_id", "chunk_index",
            "classification", "allowed_roles", "department",
            "source_path", "chunk_text"
        )
        .collect()
    )

    docs: dict[str, list[dict]] = defaultdict(list)
    doc_meta: dict[str, dict] = {}
    for row in rows:
        row_dict = row.asDict(recursive=True)
        doc_id = str(row_dict.get("document_id", ""))
        docs[doc_id].append(row_dict)
        if doc_id not in doc_meta:
            doc_meta[doc_id] = {
                "document_id": doc_id,
                "classification": row_dict.get("classification", ""),
                "allowed_roles": list(row_dict.get("allowed_roles") or []),
                "department": row_dict.get("department", ""),
                "source_path": row_dict.get("source_path", ""),
            }

    all_facts: list[dict] = []
    for doc_id, chunks in docs.items():
        sorted_chunks = sorted(chunks, key=lambda c: int(c.get("chunk_index") or 0))
        doc = {**doc_meta[doc_id], "chunks": sorted_chunks}
        all_facts.extend(_extract_facts_from_document(doc, created_at))

    schema = fact_schema()
    if not all_facts:
        return spark.createDataFrame([], schema=schema)

    schema_fields: list[StructField] = list(schema.fields or [])
    fact_rows = [
        tuple(fact[field.name] for field in schema_fields)
        for fact in all_facts
    ]
    return spark.createDataFrame(fact_rows, schema=schema)


def write_facts_jsonl(facts: Iterable[Mapping[str, Any]], facts_path: Path | str) -> None:
    """Persist extracted facts as JSON Lines."""
    resolved_path = Path(facts_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    with resolved_path.open("w", encoding="utf-8") as file_handle:
        for fact in facts:
            file_handle.write(json.dumps(dict(fact), sort_keys=True, separators=(",", ":")))
            file_handle.write("\n")


def fact_schema() -> StructType:
    """Return the Spark schema for extracted facts."""
    return StructType([
        StructField("fact_id", StringType(), False),
        StructField("fact_type", StringType(), False),
        StructField("subject", StringType(), False),
        StructField("predicate", StringType(), False),
        StructField("object", StringType(), False),
        StructField("document_id", StringType(), False),
        StructField("chunk_id", StringType(), False),
        StructField("classification", StringType(), False),
        StructField("allowed_roles", ArrayType(StringType()), False),
        StructField("department", StringType(), False),
        StructField("source_path", StringType(), False),
        StructField("confidence", DoubleType(), False),
        StructField("extraction_method", StringType(), False),
        StructField("created_at", StringType(), False)
    ])


def _extract_fact_partition(
        rows: Iterator[Row],
        created_at: str
) -> Iterator[tuple[Any, ...]]:
    schema_fields: list[StructField] = list(fact_schema().fields or [])
    for row in rows:
        for fact in extract_facts_from_chunk(row.asDict(), created_at):
            yield tuple(fact[field.name] for field in schema_fields)


def _extract_facts_from_document(
        doc: dict[str, Any],
        created_at: str
) -> list[dict[str, Any]]:
    """Extract structured facts from a document's reconstructed full text.

    ``doc`` is expected to have a ``chunks`` key containing a list of dicts,
    each with ``chunk_index``, ``chunk_id``, and ``chunk_text`` fields.
    Chunks are assumed to already be sorted by ``chunk_index``.
    """
    chunks = doc.get("chunks") or []
    combined_text = "\n".join(
        chunk.get("chunk_text") or ""
        for chunk in chunks
        if chunk.get("chunk_text")
    )
    if not combined_text:
        return []

    title = _extract_incident_title(combined_text)
    commander = _extract_incident_commander(combined_text)
    if not title or not commander:
        return []

    best_chunk_id = _find_best_chunk_id(chunks, commander)
    proxy_chunk: dict[str, Any] = {
        "document_id": doc.get("document_id", ""),
        "chunk_id": best_chunk_id,
        "classification": doc.get("classification", ""),
        "allowed_roles": doc.get("allowed_roles") or [],
        "department": doc.get("department", ""),
        "source_path": doc.get("source_path", ""),
    }
    fact = ExtractedFact(
        fact_id=_fact_id(proxy_chunk, title, "incident_commander"),
        fact_type="incident_commander",
        subject=title,
        predicate="HAS_INCIDENT_COMMANDER",
        object=commander,
        document_id=str(doc.get("document_id", "")),
        chunk_id=best_chunk_id,
        classification=str(doc.get("classification", "")),
        allowed_roles=list(doc.get("allowed_roles") or []),
        department=str(doc.get("department", "")),
        source_path=str(doc.get("source_path", "")),
        confidence=0.98,
        extraction_method="regex:v1:document_aware",
        created_at=created_at
    )
    return [fact.to_record()]


def _find_best_chunk_id(chunks: list[Any], commander_email: str) -> str:
    """Return the chunk_id of the chunk containing commander_email.

    Falls back to the first chunk_id when the commander line is not found
    in any individual chunk (e.g. because chunks are too granular).
    """
    first_chunk_id = ""
    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id", ""))
        chunk_text = str(chunk.get("chunk_text") or "")
        if not first_chunk_id:
            first_chunk_id = chunk_id
        if commander_email in chunk_text:
            return chunk_id
    return first_chunk_id


def _extract_incident_title(chunk_text: str) -> str:
    match = _INCIDENT_TITLE_PATTERN.search(chunk_text)
    if match is None:
        return ""
    return match.group("title").strip()


def _extract_incident_commander(chunk_text: str) -> str:
    match = _INCIDENT_COMMANDER_PATTERN.search(chunk_text)
    if match is None:
        return ""
    return match.group("commander").strip()


def _fact_id(
        chunk: Mapping[str, Any],
        subject: str,
        fact_type: str
) -> str:
    identity = "|".join([
        str(chunk.get("document_id", "")),
        str(chunk.get("chunk_id", "")),
        fact_type,
        subject.casefold()
    ])
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"fact-{digest}"
