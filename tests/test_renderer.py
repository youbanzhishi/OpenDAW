"""
test_renderer.py — Tests for vcmix.engine.renderer.

Tests the rendering pipeline:
    - Renderer can be instantiated with a ProjectConfig
    - Empty tracks raises ValueError
    - Report and auto-fix flags work

Usage:
    pytest tests/test_renderer.py -v

Dependencies: pytest, numpy
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from vcmix.config.parser import parse_project
from vcmix.engine.renderer import Renderer


class TestRenderer:
    """Tests for Renderer."""

    def _make_project(self, tmp_path: Path, tracks: list | None = None) -> Any:
        """Helper: create a minimal ProjectConfig for testing."""
        # Generate a 1-second test WAV
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)
        wav_path = tmp_path / "test_vocal.wav"
        sf.write(str(wav_path), audio, sr)

        if tracks is None:
            tracks = [{"name": "vocal", "file": str(wav_path)}]

        yaml_content = {
            "name": "test_render",
            "bpm": 120,
            "sample_rate": 44100,
            "tracks": tracks,
            "master": {"levels": {"vocal": 1.0}, "output": str(tmp_path / "out.wav")},
        }
        import yaml
        yaml_path = tmp_path / "render_test.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(yaml_content, f)

        return parse_project(yaml_path)

    def test_instantiation(self, tmp_path: Path) -> None:
        """Renderer should accept a ProjectConfig."""
        from vcmix.config.parser import ProjectConfig
        config = ProjectConfig(name="test", tracks=[], master={"levels": {}, "output": "out.wav"})
        r = Renderer(config)
        assert r.config.name == "test"

    def test_empty_tracks_raises(self, tmp_path: Path) -> None:
        """Rendering with no tracks should raise ValueError."""
        from vcmix.config.parser import ProjectConfig
        config = ProjectConfig(name="test", tracks=[], master={"levels": {}, "output": "out.wav"})
        r = Renderer(config)
        with pytest.raises((ValueError, RuntimeError)):
            r.run()

    def test_report_flag(self, tmp_path: Path) -> None:
        """Report flag should be stored."""
        from vcmix.config.parser import ProjectConfig
        config = ProjectConfig(name="test", tracks=[], master={"levels": {}, "output": "out.wav"})
        r = Renderer(config, report=True)
        assert r.report is True

    def test_auto_fix_flag(self, tmp_path: Path) -> None:
        """Auto-fix flag should be stored."""
        from vcmix.config.parser import ProjectConfig
        config = ProjectConfig(name="test", tracks=[], master={"levels": {}, "output": "out.wav"})
        r = Renderer(config, auto_fix=True)
        assert r.auto_fix is True
