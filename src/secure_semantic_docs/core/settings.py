"""Application-wide constants."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar


class _BaseSettingsMeta(type):
    DOCSEC_PROJECT_ROOT: str
    DOCSEC_PROJECT_ROOT_LEGACY: str

    @property
    def project_root(cls) -> Path:
        """Resolve the project root directory.

        Resolution order:

        1. ``DOCSEC_PROJECT_ROOT`` environment variable.
        2. ``SSD_PROJECT_ROOT`` environment variable (legacy alias).
        3. Auto-detected as four directory levels above this file.
        """
        env_root = (
            os.environ.get(cls.DOCSEC_PROJECT_ROOT)
            or os.environ.get(cls.DOCSEC_PROJECT_ROOT_LEGACY)
        )
        return Path(env_root) if env_root else Path(__file__).resolve().parents[3]

    @property
    def resources_dir(cls) -> Path:
        """Return the path to the bundled ``resources/`` directory."""
        return Path(__file__).resolve().parent.parent / "resources"


class BaseSettings(metaclass=_BaseSettingsMeta):
    """Project-level constants shared across all modules."""

    APP_NAME = "DocSecPipeline"
    DOCSEC_PROJECT_ROOT = "DOCSEC_PROJECT_ROOT"
    DOCSEC_PROJECT_ROOT_LEGACY = "SSD_PROJECT_ROOT"

    if TYPE_CHECKING:  # pragma: no cover
        project_root: ClassVar[Path]
        resources_dir: ClassVar[Path]
