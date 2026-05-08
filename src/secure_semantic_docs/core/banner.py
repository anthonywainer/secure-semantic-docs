"""Runtime startup banner helpers."""

from __future__ import annotations

from secure_semantic_docs.core.project_metadata import load_project_metadata

_BANNER_WIDTH = 92

_ASCII_ART = [
    " ███████╗███████╗ ██████╗██╗   ██╗██████╗ ███████╗ ",
    " ██╔════╝██╔════╝██╔════╝██║   ██║██╔══██╗██╔════╝ ",
    " ███████╗█████╗  ██║     ██║   ██║██████╔╝█████╗   ",
    " ╚════██║██╔══╝  ██║     ██║   ██║██╔══██╗██╔══╝   ",
    " ███████║███████╗╚██████╗╚██████╔╝██║  ██║███████╗ ",
    " ╚══════╝╚══════╝ ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝ ",
    "                                                   ",
    " ██████╗  ██████╗  ██████╗██╗   ██╗███╗   ███╗███████╗███╗   ██╗████████╗███████╗ ",
    " ██╔══██╗██╔═══██╗██╔════╝██║   ██║████╗ ████║██╔════╝████╗  ██║╚══██╔══╝██╔════╝ ",
    " ██║  ██║██║   ██║██║     ██║   ██║██╔████╔██║█████╗  ██╔██╗ ██║   ██║   ███████╗ ",
    " ██║  ██║██║   ██║██║     ██║   ██║██║╚██╔╝██║██╔══╝  ██║╚██╗██║   ██║   ╚════██║ ",
    " ██████╔╝╚██████╔╝╚██████╗╚██████╔╝██║ ╚═╝ ██║███████╗██║ ╚████║   ██║   ███████║ ",
    " ╚═════╝  ╚═════╝  ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚══════╝ "
]


def _frame_line(content: str = "") -> str:
    """Render a single framed banner line."""
    return f"║{content:^{_BANNER_WIDTH}}║"


def build_banner() -> str:
    """Return the startup banner with version and author from ``pyproject.toml``."""
    metadata = load_project_metadata()
    banner_lines = [
        "╔" + ("═" * _BANNER_WIDTH) + "╗",
        _frame_line()
    ]
    banner_lines.extend(_frame_line(ascii_art_line) for ascii_art_line in _ASCII_ART)
    banner_lines.extend(
        [
            _frame_line(),
            _frame_line(f"{metadata.name} v{metadata.version}"),
            _frame_line(f"author {metadata.author}" if metadata.author else ""),
            _frame_line(),
            "╚" + ("═" * _BANNER_WIDTH) + "╝"
        ]
    )
    return "\n".join(banner_lines)
