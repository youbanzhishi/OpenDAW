"""
test_sidechain.py — Tests for sidechain routing in VCMix.

Tests:
    - EffectConfig with sidechain field
    - PluginAdapter.process_with_sidechain
    - Sidechain simulation logic
    - Render order resolution with sidechain dependencies
    - YAML parsing with sidechain config

Usage:
    pytest tests/test_sidechain.py -v

Dependencies: pytest, numpy
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

from vcmix.config.parser import EffectConfig, ProjectConfig, TrackConfig, parse_project
from vcmix.plugins.vc_plugins import VCPluginAdapter


class TestSidechainConfig:
    """Tests for sidechain configuration parsing."""

    def test_effect_with_sidechain(self):
        """EffectConfig should accept sidechain field."""
        effect = EffectConfig(
            name="vc-comp",
            params={"threshold": -20, "ratio": 4},
            sidechain="kick",
        )
        assert effect.sidechain == "kick"

    def test_effect_without_sidechain(self):
        """EffectConfig sidechain defaults to None."""
        effect = EffectConfig(name="vc-comp", params={"threshold": -20})
        assert effect.sidechain is None

    def test_yaml_with_sidechain(self, tmp_path: Path):
        """Parse YAML with sidechain routing."""
        # Create a dummy WAV file
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        kick_audio = 0.8 * np.sin(2 * np.pi * 60 * t)
        bass_audio = 0.5 * np.sin(2 * np.pi * 100 * t)
        kick_path = tmp_path / "kick.wav"
        bass_path = tmp_path / "bass.wav"
        sf.write(str(kick_path), kick_audio, sr)
        sf.write(str(bass_path), bass_audio, sr)

        yaml_content = {
            "name": "sidechain_test",
            "bpm": 120,
            "tracks": [
                {"name": "kick", "file": str(kick_path), "effects": []},
                {
                    "name": "bass",
                    "file": str(bass_path),
                    "effects": [
                        {
                            "name": "vc-comp",
                            "params": {"threshold": -20, "ratio": 4},
                            "sidechain": "kick",
                        }
                    ],
                },
            ],
            "master": {"levels": {"kick": 1.0, "bass": 1.0}, "output": "out.wav"},
        }
        yaml_path = tmp_path / "sidechain.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(yaml_content, f)

        cfg = parse_project(yaml_path)
        assert cfg.tracks[1].effects[0].sidechain == "kick"
        assert cfg.has_sidechain is True

    def test_project_has_sidechain_property(self):
        """ProjectConfig.has_sidechain should detect sidechain usage."""
        cfg = ProjectConfig(
            tracks=[
                TrackConfig(name="kick", file="kick.wav", effects=[]),
                TrackConfig(
                    name="bass",
                    file="bass.wav",
                    effects=[
                        EffectConfig(name="vc-comp", params={}, sidechain="kick")
                    ],
                ),
            ],
            master={"levels": {}, "output": "out.wav"},
        )
        assert cfg.has_sidechain is True

    def test_project_no_sidechain(self):
        """ProjectConfig.has_sidechain should be False without sidechain."""
        cfg = ProjectConfig(
            tracks=[
                TrackConfig(name="vocal", file="v.wav", effects=[
                    EffectConfig(name="vc-comp", params={})
                ]),
            ],
            master={"levels": {}, "output": "out.wav"},
        )
        assert cfg.has_sidechain is False


class TestSidechainProcessing:
    """Tests for sidechain audio processing."""

    def test_process_with_sidechain_none(self):
        """process_with_sidechain(None) should fall back to process()."""
        adapter = VCPluginAdapter("vc-comp")
        audio = np.ones(1000, dtype=np.float32) * 0.5
        params = {"threshold": -20, "ratio": 4}
        # Without CLI, both return passthrough audio
        result = adapter.process_with_sidechain(audio, params, sidechain_audio=None)
        # Should be same as process() — passthrough since no CLI
        assert result.shape == audio.shape

    def test_process_with_sidechain_signal(self):
        """process_with_sidechain with actual sidechain signal should run."""
        adapter = VCPluginAdapter("vc-comp")
        main_audio = np.ones(10000, dtype=np.float32) * 0.3
        sc_audio = np.ones(10000, dtype=np.float32) * 0.8
        params = {"threshold": -20, "ratio": 4}
        # Should not raise
        result = adapter.process_with_sidechain(
            main_audio, params, sample_rate=44100, sidechain_audio=sc_audio
        )
        assert result.shape == main_audio.shape

    def test_sidechain_simulation_modifies_gain(self):
        """Sidechain simulation should apply gain envelope from sidechain."""
        adapter = VCPluginAdapter("vc-comp")
        # Create a main signal and a sidechain with varying level
        sr = 44100
        main_audio = np.ones(sr, dtype=np.float32) * 0.5
        # Sidechain with a transient spike
        sc_audio = np.ones(sr, dtype=np.float32) * 0.1
        sc_audio[1000:2000] = 0.9  # Spike

        params = {"threshold": -20, "ratio": 4}
        result = adapter.process_with_sidechain(
            main_audio, params, sample_rate=sr, sidechain_audio=sc_audio
        )
        # Result should have modified gain where sidechain was loud
        assert result.shape == main_audio.shape
        # The gain should be different from the input
        assert not np.allclose(result, main_audio, atol=0.01)


class TestRenderOrder:
    """Tests for render order resolution with sidechain."""

    def test_independent_tracks_any_order(self):
        """Tracks without sidechain can be rendered in any order."""
        from vcmix.engine.renderer import Renderer
        cfg = ProjectConfig(
            tracks=[
                TrackConfig(name="vocal", file="v.wav", effects=[]),
                TrackConfig(name="accomp", file="a.wav", effects=[]),
            ],
            master={"levels": {}, "output": "out.wav"},
        )
        renderer = Renderer(cfg)
        order = renderer._resolve_render_order(cfg)
        assert set(order) == {"vocal", "accomp"}

    def test_sidechain_dependency_order(self):
        """Sidechain source must be rendered before consumer."""
        from vcmix.engine.renderer import Renderer
        cfg = ProjectConfig(
            tracks=[
                TrackConfig(name="bass", file="b.wav", effects=[
                    EffectConfig(name="vc-comp", params={}, sidechain="kick")
                ]),
                TrackConfig(name="kick", file="k.wav", effects=[]),
            ],
            master={"levels": {}, "output": "out.wav"},
        )
        renderer = Renderer(cfg)
        order = renderer._resolve_render_order(cfg)
        assert order.index("kick") < order.index("bass")

    def test_complex_sidechain_chain(self):
        """Multiple sidechain dependencies should be resolved."""
        from vcmix.engine.renderer import Renderer
        cfg = ProjectConfig(
            tracks=[
                TrackConfig(name="pad", file="p.wav", effects=[
                    EffectConfig(name="vc-comp", params={}, sidechain="kick")
                ]),
                TrackConfig(name="bass", file="b.wav", effects=[
                    EffectConfig(name="vc-comp", params={}, sidechain="kick")
                ]),
                TrackConfig(name="kick", file="k.wav", effects=[]),
            ],
            master={"levels": {}, "output": "out.wav"},
        )
        renderer = Renderer(cfg)
        order = renderer._resolve_render_order(cfg)
        assert order.index("kick") < order.index("bass")
        assert order.index("kick") < order.index("pad")
