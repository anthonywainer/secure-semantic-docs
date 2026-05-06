"""YAML file loading and deep-merge utilities."""

from pathlib import Path
from typing import Any

import yaml


def load_yaml_file(path: Path) -> dict[str, Any]:
    """Load a YAML file; return an empty dict when the file does not exist."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        result = yaml.safe_load(fh) or {}
    return result if isinstance(result, dict) else {}


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, returning a new dict."""
    result: dict[str, Any] = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
