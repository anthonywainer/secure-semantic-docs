"""Tests for the local pipeline orchestrator (demo.py)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import secure_semantic_docs.demo as demo_module
from secure_semantic_docs.demo import TaskResult, run_task


# ---------------------------------------------------------------------------
# Source-level checks
# ---------------------------------------------------------------------------

def _demo_source() -> str:
    return Path(inspect.getfile(demo_module)).read_text(encoding="utf-8")


def test_demo_has_no_print_statements() -> None:
    """demo.py must not contain any print() calls."""
    tree = ast.parse(_demo_source())
    print_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
    ]
    assert not print_calls, (
        f"Found {len(print_calls)} print() call(s) in demo.py — use logging instead"
    )


# ---------------------------------------------------------------------------
# TaskResult
# ---------------------------------------------------------------------------

def test_task_result_success_serializes() -> None:
    """TaskResult with status='success' exposes expected fields."""
    result = TaskResult(
        name="bronze_ingestion",
        status="success",
        required=True,
        duration_seconds=1.234
    )
    assert result.name == "bronze_ingestion"
    assert result.status == "success"
    assert result.required is True
    assert result.duration_seconds == 1.234
    assert result.error is None


def test_task_result_failure_serializes() -> None:
    """TaskResult with status='failed' carries the error message."""
    result = TaskResult(
        name="gold_ingestion",
        status="failed",
        required=True,
        duration_seconds=0.5,
        error="SparkSession not available"
    )
    assert result.status == "failed"
    assert result.error == "SparkSession not available"


# ---------------------------------------------------------------------------
# run_task
# ---------------------------------------------------------------------------

def test_run_task_records_success() -> None:
    """run_task returns status='success' when task_fn succeeds."""
    result = run_task("my_task", lambda: None, required=True)
    assert result.name == "my_task"
    assert result.status == "success"
    assert result.required is True
    assert result.error is None
    assert result.duration_seconds >= 0.0


def test_run_task_records_failure() -> None:
    """run_task returns status='failed' when task_fn raises."""
    def _fail() -> None:
        raise ValueError("boom")

    result = run_task("failing_task", _fail, required=True)
    assert result.status == "failed"
    assert result.error == "boom"
    assert result.duration_seconds >= 0.0


def test_run_task_optional_failure_returns_failed_status() -> None:
    """run_task marks optional failures as 'failed' without re-raising."""
    def _fail() -> None:
        raise RuntimeError("chroma unavailable")

    result = run_task("sync_chroma_index", _fail, required=False)
    assert result.status == "failed"
    assert result.required is False
    assert "chroma unavailable" in (result.error or "")


def test_run_task_does_not_raise_for_optional_failure() -> None:
    """run_task must never propagate exceptions for optional tasks."""
    def _fail() -> None:
        raise Exception("unexpected")  # noqa: TRY002

    result = run_task("optional_step", _fail, required=False)
    assert result.status == "failed"


def test_run_task_does_not_raise_for_required_failure() -> None:
    """run_task captures the exception and records it rather than re-raising."""
    def _fail() -> None:
        raise RuntimeError("required step broken")

    result = run_task("required_step", _fail, required=True)
    assert result.status == "failed"
    assert result.error is not None


# ---------------------------------------------------------------------------
# run_demo_pipeline — pipeline-level behaviour
# ---------------------------------------------------------------------------

def _make_failing_pipeline(monkeypatch: pytest.MonkeyPatch, fail_task: str) -> None:
    """Patch run_task so that *fail_task* always returns a failed result."""
    original_run_task = demo_module.run_task

    def _patched(task_name: str, task_fn, required: bool = True) -> TaskResult:
        if task_name == fail_task:
            return TaskResult(
                name=task_name,
                status="failed",
                required=required,
                duration_seconds=0.0,
                error="injected failure"
            )
        return original_run_task(task_name, task_fn, required=required)

    monkeypatch.setattr(demo_module, "run_task", _patched)


def test_required_task_failure_aborts_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed required task stops the pipeline and no further tasks are run."""
    with (
        patch("secure_semantic_docs.demo.configure_logging"),
        patch("secure_semantic_docs.demo.load_config", return_value=MagicMock()),
    ):
        _make_failing_pipeline(monkeypatch, fail_task="prepare_runtime_dirs")
        results = demo_module.run_demo_pipeline()

    attempted = [r.name for r in results]
    assert "prepare_runtime_dirs" in attempted
    assert "bronze_ingestion" not in attempted, (
        "Pipeline should have aborted before bronze_ingestion"
    )


def test_optional_task_failure_does_not_stop_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed optional task is recorded but subsequent tasks still run."""
    required_names = [
        "prepare_runtime_dirs",
        "validate_configuration",
        "validate_input_data",
        "bronze_ingestion",
        "silver_ingestion",
        "gold_ingestion",
    ]

    def _patched_run_task(task_name: str, _task_fn, required: bool = True) -> TaskResult:
        if task_name == "sync_chroma_index":
            return TaskResult(
                name=task_name,
                status="failed",
                required=False,
                duration_seconds=0.0,
                error="no server"
            )
        return TaskResult(
            name=task_name,
            status="success",
            required=required,
            duration_seconds=0.001
        )

    monkeypatch.setattr(demo_module, "run_task", _patched_run_task)

    with (
        patch("secure_semantic_docs.demo.configure_logging"),
        patch("secure_semantic_docs.demo.load_config", return_value=MagicMock()),
    ):
        results = demo_module.run_demo_pipeline()

    attempted = [r.name for r in results]
    assert "sync_chroma_index" in attempted
    assert "quality_checks" in attempted, (
        "quality_checks should still run after optional sync_chroma_index failure"
    )
    for name in required_names:
        assert name in attempted


def test_pipeline_returns_all_results_on_full_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """All 10 tasks are attempted and returned when nothing fails."""
    expected_tasks = {
        "prepare_runtime_dirs",
        "validate_configuration",
        "validate_input_data",
        "bronze_ingestion",
        "silver_ingestion",
        "gold_ingestion",
        "build_graph_or_facts",
        "sync_chroma_index",
        "export_openmetadata",
        "quality_checks",
    }

    def _always_success(task_name: str, _task_fn, required: bool = True) -> TaskResult:
        return TaskResult(
            name=task_name,
            status="success",
            required=required,
            duration_seconds=0.001
        )

    monkeypatch.setattr(demo_module, "run_task", _always_success)

    with (
        patch("secure_semantic_docs.demo.configure_logging"),
        patch("secure_semantic_docs.demo.load_config", return_value=MagicMock()),
    ):
        results = demo_module.run_demo_pipeline()

    assert {r.name for r in results} == expected_tasks
