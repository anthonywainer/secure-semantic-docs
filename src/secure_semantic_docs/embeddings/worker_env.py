"""Worker-side environment initialisation for embedding inference.

This module must be imported (and :func:`configure_worker_environment` called)
*before* any import of ``sentence_transformers`` or ``tokenizers``.

Why a separate module?
    ``_CONFIGURED`` is a module-level flag.  When Spark reuses Python worker
    processes (``spark.python.worker.reuse=true``, the default), a worker
    serves many partition calls within the same process lifetime.  The flag
    ensures the env vars are written exactly once, not once per partition.

Variables set
-------------
TOKENIZERS_PARALLELISM
    Stops HuggingFace's Rust fast tokenizer from spawning a ``loky``
    process pool inside the already-forked Spark worker subprocess.
OMP_NUM_THREADS / MKL_NUM_THREADS
    Prevents OpenMP and MKL from spinning up extra threads that compete
    with Spark's own thread model and waste CPU on single-core executor slots.
LOKY_MAX_CPU_COUNT
    Hard-caps the CPU count visible to ``loky`` so it never decides it needs
    a worker pool even if the host has many cores.

Device safety
-------------
MPS (Metal Performance Shaders, Apple Silicon) cannot be used inside a forked
Spark worker subprocess — the Metal framework crashes when accessed from a
non-main OS process.  :func:`worker_safe_device` overrides ``"mps"`` to
``"cpu"`` so the driver can resolve and log the intended device while the
worker silently falls back to a subprocess-safe alternative.
"""

import os

_CONFIGURED: bool = False
_SUBPROCESS_UNSAFE_DEVICES: frozenset[str] = frozenset({"mps"})


def configure_worker_environment() -> None:
    """Set process-level env vars required for safe embedding inference.

    Safe to call multiple times; configuration is applied only on the first
    call within each worker process.
    """
    global _CONFIGURED  # noqa: PLW0603
    if _CONFIGURED:
        return

    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["LOKY_MAX_CPU_COUNT"] = "1"

    _CONFIGURED = True


def worker_safe_device(device: str) -> str:
    """Return a device string safe for use inside a Spark worker subprocess.

    Devices in ``_SUBPROCESS_UNSAFE_DEVICES`` (currently ``"mps"``) are
    replaced with ``"cpu"``.  All other values are returned unchanged.

    Parameters
    ----------
    device:
        Resolved device string from :func:`~secure_semantic_docs.embeddings.model_loader.resolve_device`.
    """
    if device in _SUBPROCESS_UNSAFE_DEVICES:
        return "cpu"
    return device
