from __future__ import annotations

from pathlib import Path

import secure_semantic_docs.governance.retrieval as retrieval


class _SentinelResult(dict):
    pass


def test_load_wrappers_delegate_to_serving_module(monkeypatch) -> None:
    monkeypatch.setattr(retrieval, "_load_gold_records_impl", lambda path: [{"path": str(path)}])
    monkeypatch.setattr(retrieval, "_load_fact_records_impl", lambda path: [{"fact_path": str(path)}])

    assert retrieval.load_gold_records(Path("gold")) == [{"path": "gold"}]
    assert retrieval.load_fact_records(Path("facts")) == [{"fact_path": "facts"}]


def test_secure_search_uses_default_empty_users(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_secure(context, _candidates):
        captured["user"] = context.user
        captured["user_id"] = context.user_id
        captured["logs_dir"] = context.logs_dir
        return _SentinelResult(ok=True)

    monkeypatch.setattr(retrieval, "secure_retrieve", fake_secure)

    result = retrieval.secure_search("query", "ghost", [], users=None, logs_dir=tmp_path)

    assert result == {"ok": True}
    assert captured == {"user": None, "user_id": "ghost", "logs_dir": tmp_path}


def test_fact_search_uses_default_empty_users(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_fact(context, _facts):
        captured["user"] = context.user
        captured["top_k"] = context.top_k
        return {"handled": True}

    monkeypatch.setattr(retrieval, "fact_retrieve", fake_fact)

    result = retrieval.fact_search("query", "ghost", [], users=None, logs_dir=tmp_path)

    assert result == {"handled": True}
    assert captured == {"user": None, "top_k": 1}


def test_insecure_search_uses_default_empty_users(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_insecure(context, _candidates):
        captured["user"] = context.user
        captured["query"] = context.query
        return {"warning": "demo"}

    monkeypatch.setattr(retrieval, "insecure_retrieve", fake_insecure)

    result = retrieval.insecure_search("query", "ghost", [], users=None, logs_dir=tmp_path)

    assert result == {"warning": "demo"}
    assert captured == {"user": None, "query": "query"}


def test_governed_search_uses_default_empty_users(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_governed(context, _candidates, _facts):
        captured["user"] = context.user
        captured["top_k"] = context.top_k
        return {"status": "answered"}

    monkeypatch.setattr(retrieval, "governed_retrieve", fake_governed)

    result = retrieval.governed_search("query", "ghost", [], [], users=None, logs_dir=tmp_path)

    assert result == {"status": "answered"}
    assert captured == {"user": None, "top_k": 5}
