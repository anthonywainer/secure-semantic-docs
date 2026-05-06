"""Logging configuration helpers backed by ``resources/logging.ini``."""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path

_LOGGING_INI = Path(__file__).resolve().parent.parent / "resources" / "logging.ini"


def configure_logging(ini_path: Path | None = None) -> None:
    """Configure logging from an INI file.

    Parameters
    ----------
    ini_path:
        Path to a ``logging.ini`` file.  Defaults to the bundled
        ``resources/logging.ini`` when *None*.
    """
    path = ini_path or _LOGGING_INI
    logging.config.fileConfig(path, disable_existing_loggers=False)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
