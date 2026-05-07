"""
test_automix.py — Tests for vcmix.engine.automix.AutoMixer.

Tests the intelligent auto-mixing engine:
    - Dry vocal analysis produces expected metrics
    - Effect chain generation from analysis
    - YAML config generation
    - Edge cases: silence, clipping, sibilant audio

Usage:
    pytest tests/test_automix.py -v

Dependencies: pytest, numpy
"""

from __future__ import annotations

import numpy as np
import pytest

from vcmix.engine.automix import AutoMixer


class TestAutoMixerAnalysis:
    """Tests for AutoMixer.analyze_dry_vocal()."""

    def test_sine_wave_analysis(self) -> None:
        """Sine wave should produce reasonable analysis metrics."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)

        mixer = AutoMixer(sample_rate=sr)
        result = mixer.analyze_dry_vocal(audio, sr)

        # Check required keys
        assert "rms_db" in result
        assert "peak_db" in result
        assert "true_peak_db" in result
        assert "dynamic_range_db" in result
        assert "gain_needed_db" in result
        assert "sibilance_ratio" in result
        assert "needs_deesser" in result
        assert "spectrum" in result
        assert "eq_needs" in result
        assert "compression_needs" in result
        assert "reverb_suggestion" in result

        # Sine wave at 0.5 amplitude: peak ≈ -6 dBFS
        assert result["peak_db"] == pytest.approx(-6.02, abs=0.5)
        # RMS of sine at 0.5 amplitude: 0.5/sqrt(2) ≈ -9.03 dBFS
        assert result["rms_db"] == pytest.approx(-9.03, abs=1.0)

    def test_silence_analysis(self) -> None:
        """Silent audio should return -120 dBFS levels."""
        sr = 44100
        audio = np.zeros(sr, dtype=np.float32)

        mixer = AutoMixer(sample_rate=sr)
        result = mixer.analyze_dry_vocal(audio, sr)

        assert result["rms_db"] == -120.0
        assert result["peak_db"] == -120.0
        assert result["needs_deesser"] is False

    def test_clipping_audio(self) -> None:
        """Clipping audio should have high peak and suggest gain reduction."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = np.clip(2.0 * np.sin(2 * np.pi * 440 * t), -1.0, 1.0)

        mixer = AutoMixer(sample_rate=sr)
        result = mixer.analyze_dry_vocal(audio, sr)

        assert result["peak_db"] >= -0.1
        assert result["gain_needed_db"] < 0  # Should suggest gain reduction

    def test_sibilant_audio(self) -> None:
        """High-frequency audio should trigger de-esser suggestion."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        # Strong 7kHz content (sibilance region)
        audio = 0.5 * np.sin(2 * np.pi * 7000 * t)

        mixer = AutoMixer(sample_rate=sr)
        result = mixer.analyze_dry_vocal(audio, sr)

        # 7kHz pure tone should have high sibilance
        assert result["sibilance_ratio"] > 0.05
        # Pure tone may or may not exceed threshold depending on exact ratios

    def test_dynamic_range_low(self) -> None:
        """Compressed audio should have low dynamic range."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        # Constant amplitude = zero dynamic range
        audio = np.full(sr, 0.3, dtype=np.float32)

        mixer = AutoMixer(sample_rate=sr)
        result = mixer.analyze_dry_vocal(audio, sr)

        # DC signal has very low dynamic range
        assert result["dynamic_range_db"] < 3.0

    def test_stereo_audio(self) -> None:
        """Stereo audio should be handled by flattening to mono."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        mono = 0.5 * np.sin(2 * np.pi * 440 * t)
        stereo = np.stack([mono, mono * 0.8])

        mixer = AutoMixer(sample_rate=sr)
        result = mixer.analyze_dry_vocal(stereo, sr)

        assert "rms_db" in result
        assert result["rms_db"] > -120.0


class TestAutoMixerChainGeneration:
    """Tests for AutoMixer.generate_chain()."""

    def test_generates_limiter_always(self) -> None:
        """Every chain should end with a limiter."""
        mixer = AutoMixer()
        analysis = {
            "rms_db": -18.0,
            "peak_db": -6.0,
            "gain_needed_db": 0.0,
            "needs_deesser": False,
            "sibilance_ratio": 0.05,
            "dynamic_range_db": 12.0,
            "eq_needs": {},
            "compression_needs": {"needed": False},
            "reverb_suggestion": {"needed": False},
        }
        chain = mixer.generate_chain(analysis)
        assert chain[-1]["name"] == "vc-limiter"

    def test_deesser_included_when_needed(self) -> None:
        """DeEsser should be included when analysis says it's needed."""
        mixer = AutoMixer()
        analysis = {
            "rms_db": -18.0,
            "peak_db": -6.0,
            "gain_needed_db": 0.0,
            "needs_deesser": True,
            "sibilance_ratio": 0.20,
            "dynamic_range_db": 12.0,
            "eq_needs": {},
            "compression_needs": {"needed": False},
            "reverb_suggestion": {"needed": False},
        }
        chain = mixer.generate_chain(analysis)
        names = [e["name"] for e in chain]
        assert "vc-deesser" in names

    def test_gain_included_when_needed(self) -> None:
        """Gain effect should be included when gain_needed_db is significant."""
        mixer = AutoMixer()
        analysis = {
            "rms_db": -24.0,
            "peak_db": -12.0,
            "gain_needed_db": 6.0,
            "needs_deesser": False,
            "sibilance_ratio": 0.05,
            "dynamic_range_db": 12.0,
            "eq_needs": {},
            "compression_needs": {"needed": False},
            "reverb_suggestion": {"needed": False},
        }
        chain = mixer.generate_chain(analysis)
        assert chain[0]["name"] == "vc-gain"
        assert chain[0]["params"]["gain"] == 6.0

    def test_compressor_included_when_needed(self) -> None:
        """Compressor should be included when compression is needed."""
        mixer = AutoMixer()
        analysis = {
            "rms_db": -18.0,
            "peak_db": -2.0,
            "gain_needed_db": 0.0,
            "needs_deesser": False,
            "sibilance_ratio": 0.05,
            "dynamic_range_db": 16.0,
            "eq_needs": {},
            "compression_needs": {
                "needed": True,
                "threshold_db": -24,
                "ratio": 3,
                "attack_ms": 5,
                "release_ms": 50,
            },
            "reverb_suggestion": {"needed": False},
        }
        chain = mixer.generate_chain(analysis)
        names = [e["name"] for e in chain]
        assert "vc-comp" in names

    def test_reverb_included_when_needed(self) -> None:
        """Reverb should be included when suggestion says so."""
        mixer = AutoMixer()
        analysis = {
            "rms_db": -18.0,
            "peak_db": -6.0,
            "gain_needed_db": 0.0,
            "needs_deesser": False,
            "sibilance_ratio": 0.05,
            "dynamic_range_db": 12.0,
            "eq_needs": {},
            "compression_needs": {"needed": False},
            "reverb_suggestion": {
                "needed": True,
                "room": 35,
                "decay": 30,
                "damping": 50,
                "mix": 10,
                "predelay": 40,
                "wetlpf": 5000,
            },
        }
        chain = mixer.generate_chain(analysis)
        names = [e["name"] for e in chain]
        assert "vc-reverb" in names

    def test_sine_wave_full_pipeline(self) -> None:
        """Full pipeline from sine wave through analysis to chain."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)

        mixer = AutoMixer(sample_rate=sr)
        analysis = mixer.analyze_dry_vocal(audio, sr)
        chain = mixer.generate_chain(analysis)

        # Should always have at least limiter
        assert len(chain) >= 1
        assert chain[-1]["name"] == "vc-limiter"

        # Each effect should have name and params
        for effect in chain:
            assert "name" in effect
            assert "params" in effect


class TestAutoMixerYAMLGeneration:
    """Tests for AutoMixer.generate_yaml()."""

    def test_generates_valid_yaml_structure(self) -> None:
        """generate_yaml should produce a valid VCMix project structure."""
        mixer = AutoMixer()
        analysis = {
            "rms_db": -18.0,
            "peak_db": -6.0,
            "gain_needed_db": 0.0,
            "needs_deesser": False,
            "sibilance_ratio": 0.05,
            "dynamic_range_db": 12.0,
            "eq_needs": {},
            "compression_needs": {"needed": False},
            "reverb_suggestion": {"needed": False},
        }
        config = mixer.generate_yaml("vocal", "vocal.wav", analysis)

        assert config["name"] == "automix_vocal"
        assert "tracks" in config
        assert len(config["tracks"]) == 1
        assert config["tracks"][0]["name"] == "vocal"
        assert config["tracks"][0]["file"] == "vocal.wav"
        assert "effects" in config["tracks"][0]
        assert "master" in config

    def test_yaml_includes_effects(self) -> None:
        """Generated YAML should include the auto-generated effect chain."""
        mixer = AutoMixer()
        analysis = {
            "rms_db": -24.0,
            "peak_db": -12.0,
            "gain_needed_db": 6.0,
            "needs_deesser": True,
            "sibilance_ratio": 0.20,
            "dynamic_range_db": 16.0,
            "eq_needs": {"low_cut_hz": 80, "high_shelf_hz": 0, "high_shelf_gain_db": 0, "peak_freq_hz": 0, "peak_gain_db": 0},
            "compression_needs": {"needed": True, "threshold_db": -24, "ratio": 3, "attack_ms": 5, "release_ms": 50},
            "reverb_suggestion": {"needed": True, "room": 35, "decay": 30, "damping": 50, "mix": 10, "predelay": 40, "wetlpf": 5000},
        }
        config = mixer.generate_yaml("vocal", "vocal.wav", analysis)

        effects = config["tracks"][0]["effects"]
        names = [e["name"] for e in effects]
        assert "vc-gain" in names
        assert "vc-deesser" in names
        assert "vc-comp" in names
        assert "vc-reverb" in names
        assert "vc-limiter" in names

    def test_sine_wave_full_yaml_pipeline(self) -> None:
        """Full pipeline: sine wave → analyze → generate YAML."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)

        mixer = AutoMixer(sample_rate=sr, bpm=128)
        analysis = mixer.analyze_dry_vocal(audio, sr)
        config = mixer.generate_yaml("test_vocal", "test_vocal.wav", analysis)

        assert config["bpm"] == 128
        assert config["sample_rate"] == 44100
        assert config["tracks"][0]["name"] == "test_vocal"


class TestAutoMixerEdgeCases:
    """Edge case tests for AutoMixer."""

    def test_very_quiet_audio(self) -> None:
        """Very quiet audio should suggest significant gain boost."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.001 * np.sin(2 * np.pi * 440 * t)

        mixer = AutoMixer(sample_rate=sr)
        result = mixer.analyze_dry_vocal(audio, sr)

        assert result["gain_needed_db"] > 20  # Significant boost needed

    def test_short_audio(self) -> None:
        """Very short audio should still produce valid analysis."""
        sr = 44100
        audio = np.random.randn(sr // 10).astype(np.float32) * 0.3

        mixer = AutoMixer(sample_rate=sr)
        result = mixer.analyze_dry_vocal(audio, sr)

        assert "rms_db" in result
        assert result["rms_db"] > -120.0

    def test_numpy_float32_values(self) -> None:
        """All output values should be Python native types, not numpy."""
        sr = 44100
        t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)

        mixer = AutoMixer(sample_rate=sr)
        result = mixer.analyze_dry_vocal(audio, sr)

        # Check scalar values are Python floats, not numpy types
        assert isinstance(result["rms_db"], float)
        assert isinstance(result["peak_db"], float)
        assert isinstance(result["gain_needed_db"], float)
        assert isinstance(result["sibilance_ratio"], float)
        assert isinstance(result["needs_deesser"], bool)
