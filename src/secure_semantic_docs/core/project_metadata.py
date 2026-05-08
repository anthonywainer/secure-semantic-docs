"""Project metadata helpers loaded from ``pyproject.toml``."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import tomllib

from secure_semantic_docs.core.settings import BaseSettings


@dataclass(frozen=True)
class ProjectMetadata:
    """Subset of project metadata used by runtime diagnostics."""

    name: str
    version: str
    author: str


@lru_cache(maxsize=1)
def load_project_metadata() -> ProjectMetadata:
    """Load project metadata from ``pyproject.toml``."""
    pyproject_path = BaseSettings.project_root / "pyproject.toml"
    with pyproject_path.open("rb") as pyproject_file:
        pyproject_data = tomllib.load(pyproject_file)

    project_metadata_table = pyproject_data["project"]
    project_author = str(project_metadata_table.get("author") or "")
    if not project_author:
        project_authors = project_metadata_table.get("authors") or []
        if project_authors:
            primary_author = project_authors[0]
            project_author = str(primary_author.get("name") or "")

    return ProjectMetadata(
        name=str(project_metadata_table["name"]),
        version=str(project_metadata_table["version"]),
        author=project_author
    )
