"""Logging configuration helpers backed by ``resources/logging.ini``."""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path

from secure_semantic_docs.core.banner import build_banner
from secure_semantic_docs.core.settings import BaseSettings

_BANNER_EMITTED = False


def _emit_startup_banner() -> None:
    """Log the startup banner once through the application logger."""
    global _BANNER_EMITTED
    if _BANNER_EMITTED:
        return

    logger = logging.getLogger(BaseSettings.APP_NAME)
    logger.info("\n%s", build_banner())
    _BANNER_EMITTED = True


def configure_logging(ini_path: Path | None = None) -> None:
    """Configure logging from an INI file.

    Parameters
    ----------
    ini_path:
        Path to a ``logging.ini`` file.  Defaults to the bundled
        ``resources/logging.ini`` when *None*.
    """
    path: Path = ini_path or (BaseSettings.resources_dir / "logging.ini")
    logging.config.fileConfig(path, disable_existing_loggers=False)
    _emit_startup_banner()


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)


def reset_banner() -> None:
    """Reset the banner-emitted flag. Intended for use in tests only."""
    global _BANNER_EMITTED
    _BANNER_EMITTED = False
