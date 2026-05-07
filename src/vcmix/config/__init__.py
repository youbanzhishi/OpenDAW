"""
vcmix.config — YAML configuration parsing and validation.

This subpackage provides:
    - parser: Parse YAML project files into structured config dicts
    - validator: Validate config against schema rules

Usage:
    from vcmix.config import parse_project, validate_config

Dependencies: pyyaml, pydantic
"""

from vcmix.config.parser import parse_project
from vcmix.config.validator import validate_config

__all__ = ["parse_project", "validate_config"]
