"""
test_ab_compare.py — Tests for A/B comparison rendering in VCMix.

Tests:
    - TrackConfig with effects_a / effects_b
    - ProjectConfig.has_ab property
    - YAML parsing with A/B chains
    - A/B rendering mode
    - Diff analysis output

Usage:
    pytest tests/test_ab_compare.py -v

Dependencies: pytest, numpy, soundfile, pyyaml
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

from vcmix.config.parser import EffectConfig, ProjectConfig, TrackConfig, parse_project
from vcmix.engine.renderer import Renderer


class TestABConfig:
    """Tests for A/B configuration parsing."""

    def test_track_with_effects_a_b(self):
        """TrackConfig should accept effects_a and effects_b."""
        track = TrackConfig(
            name="vocal",
            file="v.wav",
            effects_a=[
                EffectConfig(name="vc-reverb", params={"room": 30, "mix": 10}),
            ],
            effects_b=[
                EffectConfig(name="vc-reverb", params={"room": 50, "mix": 20}),
            ],
        )
        assert track.effects_a is not None
        assert track.effects_b is not None
        assert len(track.effects_a) == 1
        assert len(track.effects_b) == 1

    def test_track_without_ab(self):
        """TrackConfig effects_a/b default to None."""
        track = TrackConfig(name="vocal", file="v.wav")
        assert track.effects_a is None
        assert track.effects_b is None

    def test_project_has_ab(self):
        """ProjectConfig.has_ab should detect A/B tracks."""
        cfg = ProjectConfig(
            tracks=[
                TrackConfig(
                    name="vocal",
                    file="v.wav",
                    effects_a=[EffectConfig(name="vc-reverb", params={})],
                    effects_b=[EffectConfig(name="vc-reverb", params={})],
                ),
            ],
            master={"levels": {}, "output": "out.wav"},
        )
        assert cfg.has_ab is True

    def test_project_no_ab(self):
        """ProjectConfig.has_ab should be False without A/B tracks."""
        cfg = ProjectConfig(
            tracks=[
                TrackConfig(
                    name="vocal",
                    file="v.wav",
                    effects=[EffectConfig(name="vc-reverb", params={})],
                ),
            ],
            master={"levels": {}, "output": "out.wav"},
        )
        assert cfg.has_ab is False

    def test_yaml_with_ab(self, tmp_path: Path):
        """Parse YAML with effects_a and effects_b."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)
        wav_path = tmp_path / "vocal.wav"
        sf.write(str(wav_path), audio, sr)

        yaml_content = {
            "name": "ab_test",
            "bpm": 120,
            "tracks": [
                {
                    "name": "vocal",
                    "file": str(wav_path),
                    "effects_a": [
                        {"name": "vc-reverb", "params": {"room": 30, "mix": 10}},
                    ],
                    "effects_b": [
                        {"name": "vc-reverb", "params": {"room": 50, "mix": 20}},
                    ],
                },
            ],
            "master": {"levels": {"vocal": 1.0}, "output": "out.wav"},
        }
        yaml_path = tmp_path / "ab_project.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(yaml_content, f)

        cfg = parse_project(yaml_path)
        assert cfg.has_ab is True
        assert cfg.tracks[0].effects_a is not None
        assert cfg.tracks[0].effects_b is not None
        assert cfg.tracks[0].effects_a[0].params["room"] == 30
        assert cfg.tracks[0].effects_b[0].params["room"] == 50

    def test_yaml_with_note_values_in_ab(self, tmp_path: Path):
        """Note values in A/B chains should be converted."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)
        wav_path = tmp_path / "vocal.wav"
        sf.write(str(wav_path), audio, sr)

        yaml_content = {
            "name": "ab_note_test",
            "bpm": 120,
            "tracks": [
                {
                    "name": "vocal",
                    "file": str(wav_path),
                    "effects_a": [
                        {"name": "vc-delay", "params": {"time": "1/8d"}},
                    ],
                    "effects_b": [
                        {"name": "vc-delay", "params": {"time": "1/4"}},
                    ],
                },
            ],
            "master": {"levels": {"vocal": 1.0}, "output": "out.wav"},
        }
        yaml_path = tmp_path / "ab_note.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(yaml_content, f)

        cfg = parse_project(yaml_path)
        assert cfg.tracks[0].effects_a[0].params["time"] == 375.0  # 1/8d @ 120
        assert cfg.tracks[0].effects_b[0].params["time"] == 500.0  # 1/4 @ 120


class TestABRendering:
    """Tests for A/B rendering mode."""

    def _make_ab_project(self, tmp_path: Path):
        """Helper: create a project with A/B chains."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)
        wav_path = tmp_path / "vocal.wav"
        sf.write(str(wav_path), audio, sr)

        yaml_content = {
            "name": "ab_render_test",
            "bpm": 120,
            "tracks": [
                {
                    "name": "vocal",
                    "file": str(wav_path),
                    "effects_a": [
                        {"name": "vc-gain", "params": {"gain": 3}},
                    ],
                    "effects_b": [
                        {"name": "vc-gain", "params": {"gain": -3}},
                    ],
                },
            ],
            "master": {"levels": {"vocal": 1.0}, "output": "out.wav"},
        }
        yaml_path = tmp_path / "ab_render.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(yaml_content, f)

        cfg = parse_project(yaml_path)
        cfg.__dict__["_project_dir"] = tmp_path.resolve()
        return cfg

    def test_ab_mode_flag(self):
        """Renderer should accept ab_mode flag."""
        cfg = ProjectConfig(
            name="test", tracks=[], master={"levels": {}, "output": "out.wav"}
        )
        r = Renderer(cfg, ab_mode=True)
        assert r.ab_mode is True

    def test_ab_diff_flag(self):
        """Renderer should accept ab_diff flag."""
        cfg = ProjectConfig(
            name="test", tracks=[], master={"levels": {}, "output": "out.wav"}
        )
        r = Renderer(cfg, ab_mode=True, ab_diff=True)
        assert r.ab_diff is True

    def test_render_with_ab(self, tmp_path: Path):
        """Render with --ab should produce A and B output files."""
        cfg = self._make_ab_project(tmp_path)
        renderer = Renderer(cfg, ab_mode=True, stream="none")
        output_path = renderer.run()

        # Main output should exist
        assert output_path.exists()

        # A and B outputs should exist
        output_a = output_path.with_name(output_path.stem + "_a" + output_path.suffix)
        output_b = output_path.with_name(output_path.stem + "_b" + output_path.suffix)
        assert output_a.exists(), f"A output not found: {output_a}"
        assert output_b.exists(), f"B output not found: {output_b}"

    def test_render_with_ab_diff(self, tmp_path: Path):
        """Render with --ab --diff should produce diff analysis."""
        cfg = self._make_ab_project(tmp_path)
        renderer = Renderer(cfg, ab_mode=True, ab_diff=True, stream="json")
        output_path = renderer.run()
        assert output_path.exists()

    def test_ab_outputs_valid_audio(self, tmp_path: Path):
        """A and B outputs should be valid WAV files."""
        from vcmix.audio.io import read_audio
        cfg = self._make_ab_project(tmp_path)
        renderer = Renderer(cfg, ab_mode=True, stream="none")
        output_path = renderer.run()

        output_a = output_path.with_name(output_path.stem + "_a" + output_path.suffix)
        output_b = output_path.with_name(output_path.stem + "_b" + output_path.suffix)

        audio_a, sr_a = read_audio(output_a)
        audio_b, sr_b = read_audio(output_b)

        assert sr_a == 44100
        assert sr_b == 44100
        assert len(audio_a) > 0
        assert len(audio_b) > 0

    def test_track_with_only_effects_a(self, tmp_path: Path):
        """Track with only effects_a (no effects_b) should still work."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)
        wav_path = tmp_path / "vocal.wav"
        sf.write(str(wav_path), audio, sr)

        yaml_content = {
            "name": "partial_ab",
            "bpm": 120,
            "tracks": [
                {
                    "name": "vocal",
                    "file": str(wav_path),
                    "effects": [{"name": "vc-gain", "params": {"gain": 3}}],
                    "effects_a": [
                        {"name": "vc-reverb", "params": {"room": 30}},
                    ],
                },
            ],
            "master": {"levels": {"vocal": 1.0}, "output": "out.wav"},
        }
        yaml_path = tmp_path / "partial_ab.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(yaml_content, f)

        cfg = parse_project(yaml_path)
        cfg.__dict__["_project_dir"] = tmp_path.resolve()
        renderer = Renderer(cfg, ab_mode=True, stream="none")
        # Should render without error (B uses default effects chain)
        output_path = renderer.run()
        assert output_path.exists()
