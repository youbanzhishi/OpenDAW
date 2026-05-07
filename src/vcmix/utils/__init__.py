"""
vcmix.utils — Cross-platform utility functions for VCMix.

This subpackage provides:
    - path: Cross-platform path handling utilities

Usage:
    from vcmix.utils import resolve_path, ensure_dir

Dependencies: pathlib (stdlib)
"""

from vcmix.utils.path import ensure_dir, resolve_path

__all__ = ["resolve_path", "ensure_dir"]
