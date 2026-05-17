import pytest

import secure_semantic_docs.governance as governance
from secure_semantic_docs.governance import retrieval


@pytest.mark.parametrize(
    "name,expected",
    [
        ("fact_search", retrieval.fact_search),
        ("insecure_search", retrieval.insecure_search),
        ("load_fact_records", retrieval.load_fact_records),
        ("load_gold_records", retrieval.load_gold_records),
        ("secure_search", retrieval.secure_search)
    ]
)
def test_governance_getattr_returns_retrieval_exports(name: str, expected: object) -> None:
    assert governance.__getattr__(name) is expected


def test_governance_getattr_unknown_name_raises() -> None:
    with pytest.raises(AttributeError, match="not_exported"):
        governance.__getattr__("not_exported")
