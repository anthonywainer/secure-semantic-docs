"""SentenceTransformer model loading with per-worker-process caching.

Design goals
------------
* Load the model **once per worker process** — not once per partition call.
  When Spark reuses Python workers (default), a single worker may handle
  dozens of partitions.  Reloading the model each time would dominate runtime.

* Auto-detect the best available compute device so the same config works on
  CPU-only development machines and GPU cluster executors without changes.

* Keep all heavy imports (``sentence_transformers``, ``torch``) **deferred**
  so they are not required on the Spark driver, only on executors.

Thread-safety note
------------------
Each Spark Python worker is a single-threaded process.  ``_MODEL_CACHE`` does
not need a lock.  Do not share this module's state across threads.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from secure_semantic_docs.core import BaseSettings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(BaseSettings.APP_NAME)

# Keyed by (model_name, device) so switching device within one process is safe.
_MODEL_CACHE: dict[tuple[str, str], SentenceTransformer] = {}


def resolve_device(preferred: str) -> str:
    """Return the concrete device string for *preferred*.

    ``"auto"`` probes for CUDA, then Apple MPS, then falls back to ``"cpu"``.
    Any other value is returned unchanged so callers can pin the device
    explicitly (e.g. ``"cpu"``, ``"cuda:0"``).
    """
    if preferred != "auto":
        return preferred

    try:
        import torch  # noqa: PLC0415

        cuda_available: bool = torch.cuda.is_available()
        mps_available: bool = torch.backends.mps.is_available()
    except ImportError:
        cuda_available = False
        mps_available = False

    if cuda_available:
        return "cuda"
    if mps_available:
        return "mps"
    return "cpu"


def load_cached_model(model_name: str, device: str) -> SentenceTransformer:
    """Return a :class:`~sentence_transformers.SentenceTransformer` for *model_name*.

    The model is loaded on *device* and cached in this process for the
    lifetime of the worker.  Subsequent calls with the same arguments return
    the cached instance without touching disk or network.

    Parameters
    ----------
    model_name:
        HuggingFace model identifier (e.g. ``"all-MiniLM-L6-v2"``).
    device:
        Concrete device string (``"cpu"``, ``"cuda"``, ``"mps"``).
        Call :func:`resolve_device` before this function if you need
        ``"auto"`` resolution.
    """
    key = (model_name, device)
    if key not in _MODEL_CACHE:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415

        logger.info(
            "Loading SentenceTransformer -- model=%s device=%s",
            model_name,
            device
        )
        _MODEL_CACHE[key] = SentenceTransformer(model_name, device=device)

    return _MODEL_CACHE[key]
