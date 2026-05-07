"""
path.py — Cross-platform path utilities for VCMix.

Provides path handling that works consistently across
Windows, macOS, and Linux:
    - resolve_path(): Resolve a path relative to a project root
    - ensure_dir(): Create directory tree if it doesn't exist
    - normalize_path(): Convert to platform-native path string

All path operations use pathlib for cross-platform compatibility.
Never hardcode path separators ("/" or "\\").

Usage:
    from vcmix.utils.path import resolve_path, ensure_dir
    full_path = resolve_path("audio/vocal.wav", project_root="/projects/song1")
    ensure_dir("/projects/song1/output")

Dependencies: pathlib (stdlib only)
"""

from __future__ import annotations

from pathlib import Path


def resolve_path(relative_path: str | Path, project_root: str | Path | None = None) -> Path:
    """
    Resolve a path relative to a project root directory.

    If the path is already absolute, return it as-is.
    If relative, resolve against the project root (or CWD if no root given).

    Args:
        relative_path: The path to resolve.
        project_root: Optional project root directory.

    Returns:
        Resolved absolute Path object.
    """
    path = Path(relative_path)
    if path.is_absolute():
        return path.resolve()

    root = Path(project_root) if project_root else Path.cwd()
    return (root / path).resolve()


def ensure_dir(path: str | Path) -> Path:
    """
    Ensure a directory exists, creating it and parents if needed.

    Args:
        path: Directory path to create.

    Returns:
        The resolved Path object.
    """
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path.resolve()


def normalize_path(path: str | Path) -> str:
    """
    Normalize a path to platform-native string representation.

    Args:
        path: Path to normalize.

    Returns:
        Platform-native path string.
    """
    return str(Path(path))
