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
            "tracks": [{"file": "vocal.wav"}],
            "output": {"path": "out.wav"},
        }
        yaml_path = write_yaml(config_data, tmp_path / "project.yaml")
        result = parse_project(yaml_path)
        assert result["name"] == "test_project"
        assert result["sample_rate"] == 44100
        assert result["bpm"] == 120

    def test_full_config(self, tmp_path: Path) -> None:
        """A fully-specified config should preserve all values."""
        config_data = {
            "name": "full_project",
            "sample_rate": 48000,
            "bpm": 140,
            "time_signature": "3/4",
            "tracks": [{"file": "a.wav"}, {"file": "b.wav"}],
            "master": {"gain": -1.0},
            "output": {"path": "result.wav", "format": "wav"},
        }
        yaml_path = write_yaml(config_data, tmp_path / "project.yaml")
        result = parse_project(yaml_path)
        assert result["sample_rate"] == 48000
        assert result["bpm"] == 140
        assert result["time_signature"] == "3/4"
        assert len(result["tracks"]) == 2

    def test_missing_file_raises(self) -> None:
        """Parsing a non-existent file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parse_project(Path("/nonexistent/project.yaml"))

    def test_invalid_yaml_root(self, tmp_path: Path) -> None:
        """A YAML file with a non-mapping root should raise ValueError."""
        yaml_path = tmp_path / "bad.yaml"
        yaml_path.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(ValueError, match="mapping"):
            parse_project(yaml_path)

    def test_default_name_from_filename(self, tmp_path: Path) -> None:
        """If 'name' is omitted, use the file stem."""
        config_data = {"tracks": [{"file": "a.wav"}]}
        yaml_path = write_yaml(config_data, tmp_path / "my_song.yaml")
        result = parse_project(yaml_path)
        assert result["name"] == "my_song"
