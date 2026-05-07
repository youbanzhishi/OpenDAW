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


class TestRendererDataStreamIntegration:
    """Tests for Phase 4 DataStream integration in Renderer."""

    def test_data_stream_initialized(self) -> None:
        """Renderer should initialize DataStream in __post_init__."""
        from vcmix.config.parser import ProjectConfig
        from vcmix.stream.emitter import DataStream
        config = ProjectConfig(name="test", tracks=[], master={"levels": {}, "output": "out.wav"})
        r = Renderer(config)
        assert isinstance(r.data_stream, DataStream)

    def test_data_stream_json_format(self) -> None:
        """stream='json' should create JSON DataStream."""
        from vcmix.config.parser import ProjectConfig
        from vcmix.stream.emitter import DataStream
        config = ProjectConfig(name="test", tracks=[], master={"levels": {}, "output": "out.wav"})
        r = Renderer(config, stream="json")
        assert r.data_stream.format == "json"

    def test_data_stream_dict_format(self) -> None:
        """stream='log' should create dict DataStream."""
        from vcmix.config.parser import ProjectConfig
        config = ProjectConfig(name="test", tracks=[], master={"levels": {}, "output": "out.wav"})
        r = Renderer(config, stream="log")
        assert r.data_stream.format == "dict"

    def test_get_stream_events(self) -> None:
        """get_stream_events should return events from DataStream."""
        from vcmix.config.parser import ProjectConfig
        config = ProjectConfig(name="test", tracks=[], master={"levels": {}, "output": "out.wav"})
        r = Renderer(config)
        r.data_stream.start()
        r.data_stream.emit_track_level("vocal", rms_db=-12, peak_db=-3)
        events = r.get_stream_events()
        assert len(events) >= 1

    def test_db_helper(self) -> None:
        """_db helper should convert linear to dBFS."""
        from vcmix.config.parser import ProjectConfig
        config = ProjectConfig(name="test", tracks=[], master={"levels": {}, "output": "out.wav"})
        r = Renderer(config)
        assert r._db(1.0) == pytest.approx(0.0, abs=0.01)
        assert r._db(0.5) == pytest.approx(-6.02, abs=0.1)
        assert r._db(0.0) == -120.0

    def test_render_emits_datastream_events(self, tmp_path: Path) -> None:
        """Full render should emit DataStream events for track level, effect delta, etc."""
        import soundfile as sf
        import yaml

        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)
        wav_path = tmp_path / "test_vocal.wav"
        sf.write(str(wav_path), audio, sr)

        yaml_content = {
            "name": "test_stream_render",
            "bpm": 120,
            "sample_rate": 44100,
            "tracks": [{"name": "vocal", "file": str(wav_path)}],
            "master": {"levels": {"vocal": 1.0}, "output": str(tmp_path / "out.wav")},
        }
        yaml_path = tmp_path / "render_test.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(yaml_content, f)

        cfg = parse_project(yaml_path)
        cfg.__dict__["_project_dir"] = tmp_path

        r = Renderer(cfg, stream="log")
        output = r.run()
        assert output.exists()

        # Check that DataStream accumulated events
        events = r.get_stream_events()
        event_types = [e.event_type for e in events]

        # Should have track_level events
        assert "track_level" in event_types
        # Should have master_level events
        assert "master_level" in event_types
