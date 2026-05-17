"""Secure retrieval serving layer."""

from secure_semantic_docs.serving.access_context import AccessContext
from secure_semantic_docs.serving.answer_extractor import extract_answer
from secure_semantic_docs.serving.result_sanitizer import (
    get_gold_forbidden_fields,
    sanitize_result
)
from secure_semantic_docs.serving.retrieval_service import (
    fact_retrieve,
    insecure_retrieve,
    load_fact_records,
    load_gold_records,
    secure_retrieve,
)

__all__ = [
    "AccessContext",
    "extract_answer",
    "fact_retrieve",
    "get_gold_forbidden_fields",
    "insecure_retrieve",
    "load_fact_records",
    "load_gold_records",
    "sanitize_result",
    "secure_retrieve"
]
