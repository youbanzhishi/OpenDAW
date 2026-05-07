"""
vcmix.utils — Cross-platform utility functions for VCMix.

This subpackage provides:
    - path: Cross-platform path handling utilities

Usage:
    from vcmix.utils import resolve_path, ensure_dir

Dependencies: pathlib (stdlib)
"""

from vcmix.utils.path import resolve_path, ensure_dir

__all__ = ["resolve_path", "ensure_dir"]
