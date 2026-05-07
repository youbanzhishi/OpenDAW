"""
vcmix.config — YAML project configuration parsing and validation.

This subpackage provides:
    - Pydantic data models for project/track/effect/master layers
    - YAML parser with BPM note-value auto-conversion
    - Config validation utilities

Usage:
    from vcmix.config.parser import parse_project
    cfg = parse_project("project.yaml")

Dependencies: pyyaml, pydantic
"""

from vcmix.config.parser import (
    parse_project,
    ProjectConfig,
    TrackConfig,
    EffectConfig,
    MasterConfig,
)

__all__ = ["parse_project", "ProjectConfig", "TrackConfig", "EffectConfig", "MasterConfig"]
