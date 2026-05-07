"""
test_parser.py — Tests for vcmix.config.parser.

Tests YAML parsing of project files:
    - Valid project file parses correctly
    - Missing file raises FileNotFoundError
    - Invalid YAML raises ValueError
    - Default values are applied for missing optional fields

Usage:
    pytest tests/test_parser.py -v

Dependencies: pytest, pyyaml
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from vcmix.config.parser import parse_project


def write_yaml(data: dict, path: Path) -> Path:
    """Helper: write a dict as YAML to a temp file."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
    return path


class TestParseProject:
    """Tests for parse_project()."""

    def test_valid_minimal_config(self, tmp_path: Path) -> None:
        """A minimal valid config should parse without errors."""
        config_data = {
            "name": "test_project",
            "tracks": [{"name": "vocal", "file": "vocal.wav"}],
            "master": {"levels": {"vocal": 1.0}, "output": "out.wav"},
        }
        yaml_path = write_yaml(config_data, tmp_path / "project.yaml")
        result = parse_project(yaml_path)
        assert result.name == "test_project"
        assert result.sample_rate == 44100
        assert result.bpm == 120

    def test_full_config(self, tmp_path: Path) -> None:
        """A fully-specified config should preserve all values."""
        config_data = {
            "name": "full_project",
            "sample_rate": 48000,
            "bpm": 140,
            "tracks": [
                {"name": "vocal", "file": "a.wav"},
                {"name": "bgv", "file": "b.wav"},
            ],
            "master": {"levels": {"vocal": 0.8, "bgv": 0.5}, "output": "result.wav"},
        }
        yaml_path = write_yaml(config_data, tmp_path / "full.yaml")
        result = parse_project(yaml_path)
        assert result.name == "full_project"
        assert result.sample_rate == 48000
        assert result.bpm == 140.0
        assert len(result.tracks) == 2

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """Non-existent YAML file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parse_project(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml_root(self, tmp_path: Path) -> None:
        """YAML with non-dict root should raise ValueError."""
        bad_path = tmp_path / "bad.yaml"
        bad_path.write_text("just a string", encoding="utf-8")
        with pytest.raises(ValueError):
            parse_project(bad_path)

    def test_default_name_from_filename(self, tmp_path: Path) -> None:
        """If 'name' is missing, use the YAML filename (without ext)."""
        config_data = {
            "tracks": [{"name": "vocal", "file": "a.wav"}],
            "master": {"levels": {"vocal": 1.0}, "output": "out.wav"},
        }
        yaml_path = write_yaml(config_data, tmp_path / "my_project.yaml")
        result = parse_project(yaml_path)
        assert result.name == "Untitled"  # parser defaults to "Untitled" when name omitted
